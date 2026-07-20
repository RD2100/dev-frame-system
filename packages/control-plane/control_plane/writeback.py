"""Governed write-back executor for the RD-Code editor loop (M8.2).

The bridge default policy stays read-only. A write-back is a per-action,
human-gated, audited exception: the dashboard POST endpoints
(``/api/t3/approval-response`` approve, or ``/actions/execute`` with
``confirm=execute``) own the human gate, and this module owns ONLY the safe
filesystem write plus an audit record. This executor must never be reachable
without that gate.

Safety contract (enforced here, independent of the caller):
- The target must resolve to a path strictly under the workspace root.
- Absolute paths, drive-qualified paths, and any ``..`` segment are rejected.
- Sensitive path components are refused (``.git``, ``.env*``, key/credential
  stores, generated runtime/state dirs, ``node_modules``).
- Symlinks (the target itself or any ancestor pointing outside the root) are
  rejected so a write can never escape the workspace through a link.
- Contents must be a UTF-8 string under a size cap.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import threading
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

DEFAULT_MAX_WRITEBACK_BYTES = 2_000_000

# Directory/file name components we refuse to write into, case-insensitive.
_SENSITIVE_PATH_PARTS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".ssh",
        ".gnupg",
        ".aws",
        ".codexpro",
        ".cloudflared",
        ".devframe-runtime",
        ".codegraph",
        "node_modules",
        "id_rsa",
        "credentials",
        "secrets",
    }
)


class WritebackError(Exception):
    """Raised when a proposed write-back is unsafe or invalid."""


def _is_env_like(part: str) -> bool:
    lowered = part.lower()
    return lowered == ".env" or lowered.startswith(".env.") or lowered.endswith(".env")


def _is_sensitive_part(part: str) -> bool:
    # Windows silently strips trailing dots/spaces (".git " -> ".git"), so
    # normalize before comparing or the sensitive-name guard can be bypassed.
    norm = part.rstrip(" .").lower()
    if not norm:
        return False
    return norm in _SENSITIVE_PATH_PARTS or _is_env_like(norm)


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction and is_junction():
            return True
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _same_physical_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _windows_final_path_from_os_handle(os_handle: int) -> Path:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    get_final_path.restype = wintypes.DWORD
    size = 260
    while True:
        buffer = ctypes.create_unicode_buffer(size)
        length = get_final_path(os_handle, buffer, size, 0)
        if length == 0:
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error))
        if length < size:
            value = buffer.value
            if value.startswith("\\\\?\\UNC\\"):
                value = "\\\\" + value[8:]
            elif value.startswith("\\\\?\\"):
                value = value[4:]
            return Path(value)
        size = length + 1


def _final_path_from_handle(handle: BinaryIO) -> Path:
    if os.name == "nt":
        import msvcrt

        return _windows_final_path_from_os_handle(msvcrt.get_osfhandle(handle.fileno()))
    if sys.platform.startswith("linux"):
        return Path(os.readlink(f"/proc/self/fd/{handle.fileno()}"))
    if sys.platform == "darwin":
        import fcntl

        raw = fcntl.fcntl(handle.fileno(), fcntl.F_GETPATH, b"\0" * 1024)
        if not isinstance(raw, bytes):
            raise OSError("Darwin F_GETPATH returned a non-bytes path")
        terminator = raw.find(b"\0")
        if terminator <= 0:
            raise OSError("Darwin F_GETPATH returned an invalid path")
        return Path(os.fsdecode(raw[:terminator]))
    raise OSError(f"final handle path resolution is unsupported on {sys.platform}")


def _stable_file_state(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _workspace_root_identity(workspace_root: str | Path) -> dict[str, int | str]:
    try:
        root = Path(workspace_root).resolve(strict=True)
        state = root.stat()
    except (OSError, RuntimeError) as exc:
        raise WritebackError("workspace root identity is unavailable") from exc
    if not stat.S_ISDIR(state.st_mode):
        raise WritebackError("workspace root is not a directory")
    return {
        "resolved_path": str(root),
        "device": int(state.st_dev),
        "inode": int(state.st_ino),
    }


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _proposal_request_id(request_nonce: str, preview: dict[str, Any]) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", request_nonce):
        raise WritebackError("write-back proposal request nonce is invalid")
    return "wb-" + _canonical_json_sha256(
        {"request_nonce": request_nonce, "preview": preview}
    )[:16]


def _require_workspace_root_identity(
    workspace_root: str | Path,
    expected: object,
    *,
    source: bool = False,
) -> None:
    message = (
        "write-back source root changed after proposal"
        if source
        else "write-back workspace root changed after proposal"
    )
    if not isinstance(expected, dict):
        raise WritebackError(message)
    try:
        current = _workspace_root_identity(workspace_root)
    except WritebackError as exc:
        raise WritebackError(message) from exc
    if current != expected:
        raise WritebackError(message)


def read_bounded_workspace_file(
    workspace_root: str | Path,
    relative_path: str,
    *,
    max_bytes: int,
) -> bytes:
    """Read one file only when its opened handle stays bound to the safe path."""
    target = safe_resolve_workspace_path(workspace_root, relative_path)
    try:
        handle = target.open("rb")
    except OSError as exc:
        raise WritebackError("workspace file is unavailable") from exc
    try:
        with handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise WritebackError("workspace target is not a regular file")
            final_path = _final_path_from_handle(handle)
            if not _same_physical_path(final_path, target):
                raise WritebackError("workspace file handle escaped the approved path")
            if before.st_size > max_bytes:
                raise WritebackError("workspace file exceeds the size limit")
            data = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
    except WritebackError:
        raise
    except OSError as exc:
        raise WritebackError("workspace file changed during handle-bound read") from exc
    if len(data) > max_bytes:
        raise WritebackError("workspace file exceeds the size limit")
    if _stable_file_state(before) != _stable_file_state(after):
        raise WritebackError("workspace file changed during handle-bound read")
    return data


def safe_resolve_workspace_path(workspace_root: str | Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` under ``workspace_root`` or raise WritebackError.

    The returned path is guaranteed (symlinks resolved) to be strictly under the
    real workspace root.
    """
    try:
        root = Path(workspace_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WritebackError(f"workspace root is not accessible: {exc}") from exc
    if not root.is_dir():
        raise WritebackError("workspace root is not a directory")

    rel = str(relative_path or "").strip()
    if not rel:
        raise WritebackError("relative path is required")

    candidate = Path(rel)
    if candidate.is_absolute() or candidate.drive or candidate.anchor:
        raise WritebackError("relative path must be workspace-relative, not absolute")

    parts = candidate.parts
    if not parts:
        raise WritebackError("relative path is required")
    for part in parts:
        if part == "..":
            raise WritebackError("relative path must not contain '..'")
        if part in {".", ""}:
            continue
        if _is_sensitive_part(part):
            raise WritebackError(f"refusing to write sensitive path component: {part}")

    target = root / candidate

    # Reject if any existing ancestor (or the target) is a symlink, which could
    # redirect the write outside the workspace even if names look clean.
    probe = target
    while True:
        if probe == root:
            break
        if _is_link_or_reparse(probe):
            raise WritebackError("refusing to write through a symlink or reparse point (including junction)")
        parent = probe.parent
        if parent == probe:
            break
        probe = parent

    # Final guard: the fully resolved path must stay under the resolved root.
    resolved = target.resolve()
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        raise WritebackError("resolved path escapes the workspace root") from exc
    # Re-check sensitive names against the RESOLVED components: this catches
    # Windows 8.3 short names (e.g. GIT~1 -> .git) that look innocuous before
    # resolution but expand into a sensitive directory.
    for part in relative_parts:
        if _is_sensitive_part(part):
            raise WritebackError(f"refusing to write sensitive path component: {part}")
    logical_parts = tuple(part for part in parts if part not in {".", ""})
    if os.path.normcase(str(Path(*logical_parts))) != os.path.normcase(
        str(Path(*relative_parts))
    ):
        raise WritebackError("resolved path differs from the requested logical path")
    return resolved


def _close_windows_handle(os_handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    close_handle(os_handle)


def _open_windows_directory_guard(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x00000020 | 0x00000080,
        0x00000001 | 0x00000002,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        raise WritebackError("workspace directory could not be locked") from OSError(
            error,
            ctypes.FormatError(error),
        )
    try:
        if _is_link_or_reparse(path) or not path.is_dir():
            raise WritebackError("workspace directory is not a plain directory")
        if not _same_physical_path(_windows_final_path_from_os_handle(handle), path):
            raise WritebackError("workspace directory handle escaped the approved path")
    except Exception:
        _close_windows_handle(handle)
        raise
    return handle


def _guard_windows_directory_chain(root: Path, parent: Path) -> list[int]:
    handles: list[int] = []
    current = root
    try:
        handles.append(_open_windows_directory_guard(current))
        for part in parent.relative_to(root).parts:
            current = current / part
            if not current.exists():
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
            handles.append(_open_windows_directory_guard(current))
    except Exception:
        for handle in reversed(handles):
            _close_windows_handle(handle)
        raise
    return handles


def _create_windows_temporary_file(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80000000 | 0x40000000 | 0x00010000 | 0x00000080,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        1,
        0x00000080,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        raise WritebackError("temporary write file could not be created") from OSError(
            error,
            ctypes.FormatError(error),
        )
    return handle


def _write_windows_handle(os_handle: int, data: bytes) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    write_file = kernel32.WriteFile
    write_file.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    write_file.restype = wintypes.BOOL
    flush_file = kernel32.FlushFileBuffers
    flush_file.argtypes = [wintypes.HANDLE]
    flush_file.restype = wintypes.BOOL
    if data:
        buffer = ctypes.create_string_buffer(data)
        written = wintypes.DWORD()
        if not write_file(os_handle, buffer, len(data), ctypes.byref(written), None):
            error = ctypes.get_last_error()
            raise WritebackError("temporary write failed") from OSError(
                error,
                ctypes.FormatError(error),
            )
        if written.value != len(data):
            raise WritebackError("temporary write was incomplete")
    if not flush_file(os_handle):
        error = ctypes.get_last_error()
        raise WritebackError("temporary write could not be flushed") from OSError(
            error,
            ctypes.FormatError(error),
        )


def _rename_windows_handle(
    os_handle: int,
    target: Path,
    *,
    replace: bool,
) -> None:
    import ctypes
    from ctypes import wintypes

    class FileRenameInfo(ctypes.Structure):
        _fields_ = [
            ("replace_if_exists", wintypes.BOOLEAN),
            ("root_directory", wintypes.HANDLE),
            ("file_name_length", wintypes.DWORD),
            ("file_name", wintypes.WCHAR * 1),
        ]

    encoded_name = str(target).encode("utf-16-le")
    size = ctypes.sizeof(FileRenameInfo) + len(encoded_name)
    buffer = ctypes.create_string_buffer(size)
    info = FileRenameInfo.from_buffer(buffer)
    info.replace_if_exists = bool(replace)
    info.root_directory = None
    info.file_name_length = len(encoded_name)
    ctypes.memmove(
        ctypes.addressof(buffer) + FileRenameInfo.file_name.offset,
        encoded_name,
        len(encoded_name),
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    set_information.restype = wintypes.BOOL
    if not set_information(os_handle, 3, buffer, size):
        error = ctypes.get_last_error()
        message = "create-only target already exists" if error in {80, 183} else "atomic publish failed"
        raise WritebackError(message) from OSError(error, ctypes.FormatError(error))


def _set_windows_delete_on_close(os_handle: int, enabled: bool) -> None:
    import ctypes
    from ctypes import wintypes

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = [("delete_file", wintypes.BOOLEAN)]

    info = FileDispositionInfo(bool(enabled))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    set_information.restype = wintypes.BOOL
    if not set_information(os_handle, 4, ctypes.byref(info), ctypes.sizeof(info)):
        error = ctypes.get_last_error()
        raise WritebackError("temporary delete disposition could not be updated") from OSError(
            error,
            ctypes.FormatError(error),
        )


def _publish_windows(
    root: Path,
    target: Path,
    data: bytes,
    *,
    create_only: bool,
    pre_publish_check: Callable[[], None] | None,
) -> None:
    handles = _guard_windows_directory_chain(root, target.parent)
    tmp = target.parent / (
        target.name + f".devframe-writeback-{secrets.token_hex(8)}.tmp"
    )
    file_handle: int | None = None
    committed = False
    try:
        file_handle = _create_windows_temporary_file(tmp)
        if not _same_physical_path(_windows_final_path_from_os_handle(file_handle), tmp):
            raise WritebackError("temporary write handle escaped the approved path")
        _write_windows_handle(file_handle, data)
        if not _same_physical_path(
            _windows_final_path_from_os_handle(handles[-1]),
            target.parent,
        ):
            raise WritebackError("workspace directory changed before atomic publish")
        if pre_publish_check is not None:
            pre_publish_check()
        _rename_windows_handle(
            file_handle,
            target,
            replace=not create_only,
        )
        if not _same_physical_path(_windows_final_path_from_os_handle(file_handle), target):
            raise WritebackError("published file handle escaped the approved path")
        if not _same_physical_path(
            _windows_final_path_from_os_handle(handles[-1]),
            target.parent,
        ):
            raise WritebackError("workspace directory changed during atomic publish")
        if pre_publish_check is not None:
            pre_publish_check()
        committed = True
    finally:
        if file_handle is not None:
            try:
                if not committed:
                    _set_windows_delete_on_close(file_handle, True)
            finally:
                _close_windows_handle(file_handle)
        for handle in reversed(handles):
            _close_windows_handle(handle)


def _posix_final_path_from_fd(file_descriptor: int) -> Path:
    if sys.platform.startswith("linux"):
        return Path(os.readlink(f"/proc/self/fd/{file_descriptor}"))
    if sys.platform == "darwin":
        import fcntl

        raw = fcntl.fcntl(file_descriptor, fcntl.F_GETPATH, b"\0" * 1024)
        if not isinstance(raw, bytes):
            raise OSError("Darwin F_GETPATH returned a non-bytes path")
        terminator = raw.find(b"\0")
        if terminator <= 0:
            raise OSError("Darwin F_GETPATH returned an invalid path")
        return Path(os.fsdecode(raw[:terminator]))
    raise WritebackError(f"directory-bound publish is unsupported on {sys.platform}")


def _open_posix_directory_chain(root: Path, parent: Path) -> list[int]:
    if not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        raise WritebackError(f"directory-bound publish is unsupported on {sys.platform}")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    current = root
    try:
        descriptors.append(os.open(root, flags))
        for part in parent.relative_to(root).parts:
            current = current / part
            try:
                descriptor = os.open(part, flags, dir_fd=descriptors[-1])
            except FileNotFoundError:
                os.mkdir(part, dir_fd=descriptors[-1])
                descriptor = os.open(part, flags, dir_fd=descriptors[-1])
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise WritebackError("workspace directory is not a plain directory")
            descriptors.append(descriptor)
        if not _same_physical_path(_posix_final_path_from_fd(descriptors[-1]), current):
            raise WritebackError("workspace directory handle escaped the approved path")
    except Exception:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise
    return descriptors


def _publish_posix(
    root: Path,
    target: Path,
    data: bytes,
    *,
    create_only: bool,
    target_mode: int | None,
    pre_publish_check: Callable[[], None] | None,
) -> None:
    descriptors = _open_posix_directory_chain(root, target.parent)
    parent_fd = descriptors[-1]
    token = secrets.token_hex(8)
    tmp_name = target.name + f".devframe-writeback-{token}.tmp"
    backup_name = target.name + f".devframe-writeback-{token}.bak"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    temp_created = False
    backup_created = False
    target_created = False
    committed = False
    try:
        create_mode = 0o600 if create_only else 0o666
        file_descriptor = os.open(tmp_name, flags, create_mode, dir_fd=parent_fd)
        temp_created = True
        with os.fdopen(file_descriptor, "wb") as handle:
            if target_mode is not None:
                os.fchmod(handle.fileno(), target_mode)
            expected_tmp = target.parent / tmp_name
            if not _same_physical_path(_final_path_from_handle(handle), expected_tmp):
                raise WritebackError("temporary write handle escaped the approved path")
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if not _same_physical_path(_posix_final_path_from_fd(parent_fd), target.parent):
            raise WritebackError("workspace directory changed before atomic publish")
        if pre_publish_check is not None:
            pre_publish_check()
        if create_only:
            try:
                os.link(
                    tmp_name,
                    target.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise WritebackError("create-only target already exists") from exc
            except OSError as exc:
                raise WritebackError("create-only atomic publish is unavailable") from exc
            target_created = True
        else:
            if target_mode is not None:
                try:
                    os.link(
                        target.name,
                        backup_name,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise WritebackError("atomic replace backup is unavailable") from exc
                backup_created = True
            os.replace(
                tmp_name,
                target.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            temp_created = False
            target_created = True
        if not _same_physical_path(_posix_final_path_from_fd(parent_fd), target.parent):
            raise WritebackError("workspace directory changed during atomic publish")
        if pre_publish_check is not None:
            pre_publish_check()
        committed = True
    finally:
        cleanup_errors: list[OSError] = []
        restore_failed = False
        if target_created and not committed:
            if backup_created:
                try:
                    os.replace(
                        backup_name,
                        target.name,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    backup_created = False
                except OSError as exc:
                    restore_failed = True
                    cleanup_errors.append(exc)
            else:
                try:
                    os.unlink(target.name, dir_fd=parent_fd)
                except FileNotFoundError:
                    target_created = False
                except OSError as exc:
                    cleanup_errors.append(exc)
        if backup_created and not restore_failed:
            try:
                os.unlink(backup_name, dir_fd=parent_fd)
            except FileNotFoundError:
                backup_created = False
            except OSError as exc:
                cleanup_errors.append(exc)
        if temp_created:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                temp_created = False
            except OSError as exc:
                cleanup_errors.append(exc)
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        if cleanup_errors:
            raise WritebackError("failed to restore or remove an uncommitted write file") from cleanup_errors[0]


def _publish_workspace_bytes(
    root: Path,
    target: Path,
    data: bytes,
    *,
    create_only: bool,
    target_mode: int | None,
    pre_publish_check: Callable[[], None] | None,
) -> None:
    if os.name == "nt":
        _publish_windows(
            root,
            target,
            data,
            create_only=create_only,
            pre_publish_check=pre_publish_check,
        )
        return
    _publish_posix(
        root,
        target,
        data,
        create_only=create_only,
        target_mode=target_mode,
        pre_publish_check=pre_publish_check,
    )


def apply_single_file_writeback(
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    create_only: bool = False,
    pre_publish_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Atomically write ``contents`` to a safe path under ``workspace_root``.

    Returns an audit record describing the applied write. Raises WritebackError
    on any safety or validation failure (caller must have already passed the
    human gate before calling this).
    """
    if not isinstance(contents, str):
        raise WritebackError("contents must be a string")
    data = contents.encode("utf-8")
    if len(data) > max_bytes:
        raise WritebackError(
            f"contents exceed max write-back size ({len(data)} > {max_bytes} bytes)"
        )

    target = safe_resolve_workspace_path(workspace_root, relative_path)
    if target.exists() and target.is_dir():
        raise WritebackError("target path is an existing directory")

    existed = target.exists()
    if create_only and existed:
        raise WritebackError("create-only target already exists")
    target_state = target.stat() if existed else None
    before_size = target_state.st_size if target_state is not None else 0
    target_mode = stat.S_IMODE(target_state.st_mode) if target_state is not None else None
    root = Path(workspace_root).resolve(strict=True)
    root_identity = _workspace_root_identity(root)
    _publish_workspace_bytes(
        root,
        target,
        data,
        create_only=create_only,
        target_mode=target_mode,
        pre_publish_check=pre_publish_check,
    )

    return {
        "kind": "writeback_apply_file",
        "workspace_root": str(root),
        "relative_path": str(target.relative_to(root).as_posix()),
        "resolved_path": str(target),
        "operation": "created" if create_only or not existed else "modified",
        "bytes_written": len(data),
        "bytes_before": before_size,
        "contents_sha256": hashlib.sha256(data).hexdigest(),
        "workspace_root_identity": root_identity,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }


def _atomic_json_write(
    path: Path,
    payload: dict[str, Any],
    *,
    private: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    private_posix = private and os.name != "nt"
    if private_posix:
        path.parent.chmod(0o700)
    tmp = path.parent / (path.name + ".tmp")
    serialized = json.dumps(payload, indent=2, ensure_ascii=True)
    if private_posix:
        descriptor = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
        tmp.chmod(0o600)
    else:
        tmp.write_text(serialized, encoding="utf-8")
    os.replace(tmp, path)


def preview_single_file_writeback(
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    create_only: bool = False,
) -> dict[str, Any]:
    """Validate a proposed write-back WITHOUT writing; return a gate preview.

    Runs the full safety contract (path + size + type) so an unsafe proposal is
    rejected before it can reach the human gate. Never touches the filesystem.
    """
    if not isinstance(contents, str):
        raise WritebackError("contents must be a string")
    try:
        data = contents.encode("utf-8")
    except UnicodeError as exc:
        raise WritebackError("contents must be valid UTF-8") from exc
    if len(data) > max_bytes:
        raise WritebackError(
            f"contents exceed max write-back size ({len(data)} > {max_bytes} bytes)"
        )
    target = safe_resolve_workspace_path(workspace_root, relative_path)
    if target.exists() and target.is_dir():
        raise WritebackError("target path is an existing directory")
    root = Path(workspace_root).resolve()
    existed = target.exists()
    if create_only and existed:
        raise WritebackError("create-only target already exists")
    return {
        "kind": "writeback_apply_file",
        "workspace_root": str(root),
        "relative_path": str(target.relative_to(root).as_posix()),
        "operation": "modified" if existed else "created",
        "bytes": len(data),
        "bytes_before": target.stat().st_size if existed else 0,
    }


def workspace_file_sha256(
    workspace_root: str | Path,
    relative_path: str,
    *,
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
) -> str | None:
    """Return a bounded target hash, or ``None`` when the safe target is absent."""
    target = safe_resolve_workspace_path(workspace_root, relative_path)
    if not target.exists():
        return None
    data = read_bounded_workspace_file(
        workspace_root,
        relative_path,
        max_bytes=max_bytes,
    )
    return hashlib.sha256(data).hexdigest()


def apply_writeback_with_audit(
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    runtime_dir: str | Path | None = None,
    action_id: str | None = None,
    confirm: bool = False,
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    create_only: bool = False,
    pre_publish_check: Callable[[], None] | None = None,
    audit_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Human-gated, audited single-file write-back.

    Without ``confirm`` this returns a ``human_required`` gate preview and writes
    nothing (the caller — a CLI ``--confirm`` flag or the dashboard
    ``confirm=execute`` / approval gate — must explicitly confirm). With
    ``confirm`` it applies the write and, when ``runtime_dir`` is given, persists
    an ``action-run.json`` audit record under ``writeback-runs/``.
    """
    preview = preview_single_file_writeback(
        workspace_root,
        relative_path,
        contents,
        max_bytes=max_bytes,
        create_only=create_only,
    )
    if not confirm:
        return {
            "applied": False,
            "human_required": True,
            "confirm": "re-run with confirm=execute to apply this write-back through the human gate",
            **preview,
        }

    record = apply_single_file_writeback(
        workspace_root,
        relative_path,
        contents,
        max_bytes=max_bytes,
        create_only=create_only,
        pre_publish_check=pre_publish_check,
    )
    stamp = time.strftime("%Y%m%d-%H%M%S")
    resolved_action_id = (action_id or "").strip() or f"writeback-{stamp}"
    audit: dict[str, Any] = {
        "applied": True,
        "action_id": resolved_action_id,
        "action_run_id": stamp,
        **record,
    }
    if audit_fields:
        audit.update(audit_fields)
    if runtime_dir is not None:
        runtime_root = Path(runtime_dir).resolve()
        audit_path = runtime_root / "writeback-runs" / resolved_action_id / f"{stamp}.json"
        _atomic_json_write(audit_path, audit)
        audit["audit_path"] = str(audit_path)
    return audit


_REQUEST_ID_RE = re.compile(r"^wb-[0-9a-f]{16}$")
_PROPOSAL_THREAD_LOCKS: weakref.WeakValueDictionary[str, threading.Lock] = (
    weakref.WeakValueDictionary()
)
_PROPOSAL_THREAD_LOCKS_GUARD = threading.Lock()


def _proposals_dir(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir).resolve() / "writeback-proposals"


def _proposal_thread_lock(lock_path: Path) -> threading.Lock:
    key = os.path.normcase(str(lock_path))
    with _PROPOSAL_THREAD_LOCKS_GUARD:
        return _PROPOSAL_THREAD_LOCKS.setdefault(key, threading.Lock())


def _claim_writeback_proposal(
    runtime_dir: str | Path,
    request_id: str,
) -> tuple[BinaryIO, threading.Lock] | None:
    """Acquire a crash-released OS lock plus an in-process thread lock."""
    directory = _proposals_dir(runtime_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / f"{request_id}.lock"
    thread_lock = _proposal_thread_lock(lock_path)
    if not thread_lock.acquire(blocking=False):
        return None
    try:
        handle = lock_path.open("a+b")
    except OSError as exc:
        thread_lock.release()
        raise WritebackError("write-back proposal decision could not be claimed") from exc
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        thread_lock.release()
        busy_errors = {errno.EACCES, errno.EAGAIN, getattr(errno, "EDEADLK", errno.EACCES)}
        if exc.errno in busy_errors:
            return None
        raise WritebackError("write-back proposal decision lock is unavailable") from exc
    return handle, thread_lock


def _safe_request_id(request_id: str) -> str:
    rid = str(request_id or "").strip()
    if not _REQUEST_ID_RE.match(rid):
        raise WritebackError("invalid write-back request id")
    return rid


def stage_writeback_proposal(
    runtime_dir: str | Path,
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    thread_id: str = "",
    project_id: str = "",
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    redact_paths: bool = False,
    create_only: bool = False,
    proposal_kind: str = "writeback",
    source_preconditions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Validate and stage a proposed write-back as a pending, human-gated item.

    Staging never writes to the workspace; it records the proposal so a later
    human approval can apply it. Returns ``{request_id, preview}``.
    """
    preview = preview_single_file_writeback(
        workspace_root,
        relative_path,
        contents,
        max_bytes=max_bytes,
        create_only=create_only,
    )
    kind = str(proposal_kind or "").strip()
    if not re.fullmatch(r"[a-z0-9_.-]{1,80}", kind):
        raise WritebackError("invalid write-back proposal kind")
    workspace_identity = _workspace_root_identity(workspace_root)
    normalized_preconditions: list[dict[str, Any]] = []
    for raw in source_preconditions or []:
        if not isinstance(raw, dict):
            raise WritebackError("invalid write-back source precondition")
        source_root = str(raw.get("workspace_root") or "").strip()
        source_path = str(raw.get("relative_path") or "").strip()
        expected_sha256 = str(raw.get("sha256") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise WritebackError("invalid write-back source precondition hash")
        source_target = safe_resolve_workspace_path(source_root, source_path)
        current_sha256 = workspace_file_sha256(source_root, source_path)
        if current_sha256 != expected_sha256:
            raise WritebackError("write-back source changed before proposal")
        source_identity = _workspace_root_identity(source_root)
        source_root_path = Path(str(source_identity["resolved_path"]))
        normalized_preconditions.append(
            {
                "workspace_root": str(source_root_path),
                "workspace_root_identity": source_identity,
                "relative_path": source_target.relative_to(source_root_path).as_posix(),
                "sha256": expected_sha256,
            }
        )
    proposal_preview = {
        **preview,
        "contents_sha256": hashlib.sha256(contents.encode("utf-8")).hexdigest(),
        "workspace_root_identity_sha256": _canonical_json_sha256(workspace_identity),
        "source_preconditions_sha256": _canonical_json_sha256(normalized_preconditions),
        "create_only": bool(create_only),
        "proposal_kind": kind,
        "project_id": str(project_id or ""),
        "thread_id": str(thread_id or ""),
        "redact_paths": bool(redact_paths),
    }
    request_nonce = secrets.token_hex(16)
    request_id = _proposal_request_id(request_nonce, proposal_preview)
    proposal = {
        "request_id": request_id,
        "status": "pending",
        "workspace_root": str(workspace_identity["resolved_path"]),
        "workspace_root_identity": workspace_identity,
        "relative_path": preview["relative_path"],
        "contents": contents,
        "thread_id": str(thread_id or ""),
        "project_id": str(project_id or ""),
        "preview": proposal_preview,
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "redact_paths": bool(redact_paths),
        "create_only": bool(create_only),
        "proposal_kind": kind,
        "source_preconditions": normalized_preconditions,
        "request_nonce": request_nonce,
    }
    _atomic_json_write(
        _proposals_dir(runtime_dir) / f"{request_id}.json",
        proposal,
        private=bool(redact_paths),
    )
    return {"request_id": request_id, "preview": proposal_preview}


def load_writeback_proposal(runtime_dir: str | Path, request_id: str) -> dict[str, Any] | None:
    rid = _safe_request_id(request_id)
    path = _proposals_dir(runtime_dir) / f"{rid}.json"
    if not path.is_file():
        return None
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(proposal, dict):
        return None
    if proposal.get("request_id") != rid:
        raise WritebackError("write-back proposal request id does not match requested id")
    return proposal


def _validate_staged_proposal(proposal: dict[str, Any]) -> None:
    contents = proposal.get("contents")
    preview = proposal.get("preview")
    if not isinstance(contents, str) or not isinstance(preview, dict):
        raise WritebackError("write-back proposal does not match the human preview")
    try:
        data = contents.encode("utf-8")
    except UnicodeError as exc:
        raise WritebackError("write-back proposal contents must be valid UTF-8") from exc
    expected = {
        "workspace_root": proposal.get("workspace_root"),
        "relative_path": proposal.get("relative_path"),
        "contents_sha256": hashlib.sha256(data).hexdigest(),
        "workspace_root_identity_sha256": _canonical_json_sha256(
            proposal.get("workspace_root_identity")
        ),
        "source_preconditions_sha256": _canonical_json_sha256(
            proposal.get("source_preconditions")
        ),
        "create_only": bool(proposal.get("create_only")),
        "proposal_kind": proposal.get("proposal_kind"),
        "project_id": str(proposal.get("project_id") or ""),
        "thread_id": str(proposal.get("thread_id") or ""),
        "redact_paths": bool(proposal.get("redact_paths")),
    }
    if preview.get("bytes") != len(data) or any(
        preview.get(key) != value for key, value in expected.items()
    ):
        raise WritebackError("write-back proposal does not match the human preview")
    request_nonce = proposal.get("request_nonce")
    if not isinstance(request_nonce, str):
        raise WritebackError("write-back proposal request binding is invalid")
    if proposal.get("request_id") != _proposal_request_id(request_nonce, preview):
        raise WritebackError("write-back proposal request id binding is invalid")
    _require_workspace_root_identity(
        str(proposal.get("workspace_root") or ""),
        proposal.get("workspace_root_identity"),
    )


def _effective_proposal_validator(
    proposal: dict[str, Any],
    proposal_validator: Callable[[dict[str, Any]], object] | None,
) -> Callable[[dict[str, Any]], object] | None:
    if proposal_validator is not None:
        return proposal_validator
    if str(proposal.get("proposal_kind") or "") == "obsidian_project_plan":
        from .obsidian_memory import _validate_project_plan_proposal

        return _validate_project_plan_proposal
    if str(proposal.get("proposal_kind") or "") != "writeback":
        raise WritebackError("write-back proposal kind requires a dedicated validator")
    return None


def _verify_source_preconditions(proposal: dict[str, Any]) -> None:
    preconditions = proposal.get("source_preconditions") or []
    if not isinstance(preconditions, list):
        raise WritebackError("write-back source precondition is invalid")
    for precondition in preconditions:
        if not isinstance(precondition, dict):
            raise WritebackError("write-back source precondition is invalid")
        source_root = str(precondition.get("workspace_root") or "")
        _require_workspace_root_identity(
            source_root,
            precondition.get("workspace_root_identity"),
            source=True,
        )
        current_sha256 = workspace_file_sha256(
            source_root,
            str(precondition.get("relative_path") or ""),
        )
        if current_sha256 != precondition.get("sha256"):
            raise WritebackError("write-back source changed after proposal")


def _set_proposal_status(runtime_dir: str | Path, proposal: dict[str, Any], status: str) -> None:
    rid = _safe_request_id(str(proposal.get("request_id") or ""))
    proposal = {**proposal, "status": status, "resolved_at": datetime.now(timezone.utc).isoformat()}
    _atomic_json_write(
        _proposals_dir(runtime_dir) / f"{rid}.json",
        proposal,
        private=bool(proposal.get("redact_paths")),
    )


def _require_exact_applied_create_only_proposal(proposal: dict[str, Any]) -> None:
    if not proposal.get("create_only"):
        return
    contents = proposal.get("contents")
    if not isinstance(contents, str):
        raise WritebackError("write-back proposal contents are invalid")
    expected = contents.encode("utf-8")
    try:
        published = read_bounded_workspace_file(
            str(proposal.get("workspace_root") or ""),
            str(proposal.get("relative_path") or ""),
            max_bytes=max(DEFAULT_MAX_WRITEBACK_BYTES, len(expected)),
        )
    except WritebackError as exc:
        raise WritebackError("applied create-only published bytes no longer match") from exc
    if published != expected:
        raise WritebackError("applied create-only published bytes no longer match")


def _reconcile_create_only_publication(
    runtime_dir: str | Path,
    request_id: str,
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    """Recover an exact create-only target published before terminal status."""
    if not proposal.get("create_only"):
        return None
    contents = proposal.get("contents")
    if not isinstance(contents, str):
        raise WritebackError("write-back proposal contents are invalid")
    data = contents.encode("utf-8")
    workspace_root = str(proposal.get("workspace_root") or "")
    relative_path = str(proposal.get("relative_path") or "")
    _require_workspace_root_identity(
        workspace_root,
        proposal.get("workspace_root_identity"),
    )
    current_sha256 = workspace_file_sha256(
        workspace_root,
        relative_path,
        max_bytes=max(DEFAULT_MAX_WRITEBACK_BYTES, len(data)),
    )
    if current_sha256 is None:
        return None
    expected_sha256 = hashlib.sha256(data).hexdigest()
    if current_sha256 != expected_sha256:
        raise WritebackError("create-only target exists with different contents")
    _require_workspace_root_identity(
        workspace_root,
        proposal.get("workspace_root_identity"),
    )

    root = Path(workspace_root).resolve()
    target = safe_resolve_workspace_path(root, relative_path)
    target_relative_path = target.relative_to(root).as_posix()
    expected_root_identity = proposal.get("workspace_root_identity")
    expected_source_preconditions_sha256 = _canonical_json_sha256(
        proposal.get("source_preconditions")
    )
    expected_proposal_binding_sha256 = _canonical_json_sha256(
        {"request_id": request_id, "preview": proposal.get("preview")}
    )
    audit_dir = Path(runtime_dir).resolve() / "writeback-runs" / request_id
    for audit_path in sorted(audit_dir.glob("*.json")):
        try:
            existing_audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WritebackError("existing write-back audit is invalid") from exc
        if not isinstance(existing_audit, dict):
            raise WritebackError("existing write-back audit is invalid")
        if (
            existing_audit.get("applied") is True
            and existing_audit.get("action_id") == request_id
            and existing_audit.get("kind") == "writeback_apply_file"
            and existing_audit.get("relative_path") == target_relative_path
            and existing_audit.get("operation") == "created"
            and existing_audit.get("bytes_written") == len(data)
            and existing_audit.get("contents_sha256") == expected_sha256
            and existing_audit.get("workspace_root_identity") == expected_root_identity
            and existing_audit.get("source_preconditions_sha256")
            == expected_source_preconditions_sha256
            and existing_audit.get("proposal_binding_sha256")
            == expected_proposal_binding_sha256
        ):
            _verify_source_preconditions(proposal)
            _require_workspace_root_identity(
                workspace_root,
                proposal.get("workspace_root_identity"),
            )
            try:
                published = read_bounded_workspace_file(
                    workspace_root,
                    relative_path,
                    max_bytes=max(DEFAULT_MAX_WRITEBACK_BYTES, len(data)),
                )
            except WritebackError as exc:
                raise WritebackError("published bytes changed during recovery") from exc
            if published != data:
                raise WritebackError("published bytes changed during recovery")
            return {
                **existing_audit,
                "recovered": True,
                "audit_path": str(audit_path),
            }
        raise WritebackError("existing write-back audit does not match publication")

    raise WritebackError("create-only target exists without a matching audit")


def _proposal_error_mentions_private_path(
    proposal: dict[str, Any],
    error: WritebackError,
) -> bool:
    message = str(error).replace("\\", "/").casefold()
    roots = [proposal.get("workspace_root")]
    for precondition in proposal.get("source_preconditions") or []:
        if isinstance(precondition, dict):
            roots.append(precondition.get("workspace_root"))
    for raw_root in roots:
        root = str(raw_root or "").replace("\\", "/").rstrip("/").casefold()
        if root and root in message:
            return True
    return False


def resolve_writeback_proposal(
    runtime_dir: str | Path,
    request_id: str,
    decision: str,
    *,
    expected_thread_id: str | None = None,
    proposal_validator: Callable[[dict[str, Any]], object] | None = None,
) -> dict[str, Any]:
    """Apply (approve) or discard (reject) a staged write-back proposal.

    The human gate lives at the caller (the approval endpoint); this consumes a
    proposal exactly once. When ``expected_thread_id`` is given it must match the
    proposal's recorded thread. Returns a summary describing what happened.
    """
    rid = _safe_request_id(request_id)
    if decision not in {"approve", "reject"}:
        raise WritebackError("write-back decision must be approve or reject")
    claim = _claim_writeback_proposal(runtime_dir, rid)
    if claim is None:
        proposal = load_writeback_proposal(runtime_dir, rid)
        if proposal is None:
            raise WritebackError("write-back proposal not found")
        status = str(proposal.get("status") or "")
        if status == "pending":
            raise WritebackError("write-back proposal decision is already processing")
        if status == "applied":
            _validate_staged_proposal(proposal)
            effective_validator = _effective_proposal_validator(proposal, proposal_validator)
            if effective_validator is not None:
                effective_validator(proposal)
            _require_exact_applied_create_only_proposal(proposal)
        return {
            "request_id": rid,
            "applied": False,
            "already_resolved": True,
            "status": status,
        }
    claim_handle, thread_lock = claim
    proposal: dict[str, Any] | None = None
    try:
        proposal = load_writeback_proposal(runtime_dir, rid)
        if proposal is None:
            raise WritebackError("write-back proposal not found")
        status = str(proposal.get("status") or "")
        if status != "pending":
            if status == "applied":
                _validate_staged_proposal(proposal)
                effective_validator = _effective_proposal_validator(proposal, proposal_validator)
                if effective_validator is not None:
                    effective_validator(proposal)
                _require_exact_applied_create_only_proposal(proposal)
            return {
                "request_id": rid,
                "applied": False,
                "already_resolved": True,
                "status": status,
            }
        proposal_thread = str(proposal.get("thread_id") or "")
        if (
            expected_thread_id is not None
            and proposal_thread
            and str(expected_thread_id) != proposal_thread
        ):
            raise WritebackError("write-back thread mismatch")
        if decision == "reject":
            _set_proposal_status(runtime_dir, proposal, "rejected")
            return {"request_id": rid, "applied": False, "status": "rejected"}

        _validate_staged_proposal(proposal)
        effective_validator = _effective_proposal_validator(proposal, proposal_validator)
        if effective_validator is not None:
            effective_validator(proposal)
        _verify_source_preconditions(proposal)

        def pre_publish_check() -> None:
            _validate_staged_proposal(proposal)
            if effective_validator is not None:
                effective_validator(proposal)
            _verify_source_preconditions(proposal)

        result = _reconcile_create_only_publication(runtime_dir, rid, proposal)
        if result is None:
            result = apply_writeback_with_audit(
                proposal["workspace_root"],
                proposal["relative_path"],
                proposal["contents"],
                runtime_dir=runtime_dir,
                action_id=rid,
                confirm=True,
                create_only=bool(proposal.get("create_only")),
                pre_publish_check=pre_publish_check,
                audit_fields={
                    "source_preconditions_sha256": _canonical_json_sha256(
                        proposal.get("source_preconditions")
                    ),
                    "proposal_binding_sha256": _canonical_json_sha256(
                        {"request_id": rid, "preview": proposal.get("preview")}
                    ),
                },
            )
        _set_proposal_status(runtime_dir, proposal, "applied")
        response = {"request_id": rid, "applied": True, "status": "applied", **result}
        if proposal.get("redact_paths"):
            for key in (
                "workspace_root",
                "workspace_root_identity",
                "resolved_path",
                "audit_path",
            ):
                response.pop(key, None)
        return response
    except WritebackError as exc:
        if (
            proposal is not None
            and proposal.get("redact_paths")
            and _proposal_error_mentions_private_path(proposal, exc)
        ):
            raise WritebackError("redacted write-back proposal could not be resolved") from exc
        raise
    finally:
        claim_handle.close()
        thread_lock.release()


def list_pending_writeback_proposals(runtime_dir: str | Path) -> list[dict[str, Any]]:
    """Return pending (not yet approved/rejected) write-back proposals."""
    directory = _proposals_dir(runtime_dir)
    if not directory.is_dir():
        return []
    pending: list[dict[str, Any]] = []
    for path in sorted(directory.glob("wb-*.json")):
        try:
            proposal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(proposal, dict):
            continue
        if str(proposal.get("status") or "") != "pending":
            continue
        preview = proposal.get("preview")
        if proposal.get("redact_paths") and isinstance(preview, dict):
            preview = {key: value for key, value in preview.items() if key != "workspace_root"}
        pending.append(
            {
                "request_id": proposal.get("request_id"),
                "relative_path": proposal.get("relative_path"),
                "project_id": proposal.get("project_id"),
                "thread_id": proposal.get("thread_id"),
                "preview": preview,
                "staged_at": proposal.get("staged_at"),
            }
        )
    return pending
