"""Deterministic RD-Code desktop instance contract.

The instance specification is the only launch-time source for DevFrame URLs,
desktop storage, ports, build identity, readiness, and process evidence.  It
contains no credentials and is written below the selected DevFrame runtime.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .backup_guard import default_runtime_dir


DEFAULT_RDCODE_INSTANCE_ID = "rdcode-default"
DEFAULT_T3_BACKEND_PORT = 13773
DEFAULT_RDCODE_CDP_PORT = 8315
DEFAULT_READINESS_TIMEOUT_SECONDS = 90

_INSTANCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BUILD_INPUTS = (
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "tsconfig.base.json",
    "vite.config.ts",
    "apps/desktop",
    "apps/server",
    "apps/web",
    "packages",
    "scripts",
)
_IGNORED_BUILD_PARTS = {"node_modules", "dist", "dist-electron", ".vite-plus", "tmp", ".electron-runtime"}
_LEASED_INSTANCE_STATUSES = {
    "ready",
    "degraded",
    "planned",
    "building",
    "build-reused",
    "starting",
    "stopping",
}
_SPEC_WRITE_LOCK = threading.Lock()


class RdCodeInstanceError(ValueError):
    """Raised when an RD-Code instance contract is unsafe or inconsistent."""


def build_rdcode_instance_spec(
    *,
    runtime_dir: str | Path | None,
    t3_root: str | Path,
    host: str,
    control_plane_port: int,
    renderer_environment: dict[str, Any],
    instance_id: str = DEFAULT_RDCODE_INSTANCE_ID,
    t3_backend_port: int = DEFAULT_T3_BACKEND_PORT,
    cdp_port: int = DEFAULT_RDCODE_CDP_PORT,
    readiness_timeout_seconds: int = DEFAULT_READINESS_TIMEOUT_SECONDS,
    exit_after_ready_seconds: int = 0,
    force_build: bool = False,
) -> dict[str, Any]:
    """Build a validated, self-contained desktop instance specification."""
    normalized_id = _validate_instance_id(instance_id)
    normalized_host = _validate_loopback_host(host)
    ports = {
        "controlPlane": _validate_port("control_plane_port", control_plane_port),
        "t3Backend": _validate_port("t3_backend_port", t3_backend_port),
        "cdp": _validate_port("cdp_port", cdp_port),
    }
    if len(set(ports.values())) != len(ports):
        raise RdCodeInstanceError("control-plane, T3 backend, and CDP ports must be distinct")
    if readiness_timeout_seconds < 1 or readiness_timeout_seconds > 600:
        raise RdCodeInstanceError("readiness_timeout_seconds must be between 1 and 600")
    if exit_after_ready_seconds < 0 or exit_after_ready_seconds > 600:
        raise RdCodeInstanceError("exit_after_ready_seconds must be between 0 and 600")
    if not isinstance(force_build, bool):
        raise RdCodeInstanceError("force_build must be a boolean")

    root = Path(t3_root).resolve()
    if not (root / "package.json").is_file() or not (root / "apps" / "web").is_dir():
        raise RdCodeInstanceError(f"invalid T3 checkout: {root}")
    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    instance_dir = (runtime_root / "rd-code" / "instances" / normalized_id).resolve()
    paths = _build_instance_paths(root, instance_dir)
    base_url = _loopback_base_url(normalized_host, ports["controlPlane"])
    renderer_env = _build_renderer_environment(renderer_environment, base_url)
    desktop_env = {
        "APPDATA": paths["appDataDir"],
        "LOCALAPPDATA": paths["localAppDataDir"],
        "T3CODE_HOME": paths["t3Home"],
        "T3CODE_PORT": str(ports["t3Backend"]),
        "T3CODE_DESKTOP_APP_USER_MODEL_ID": f"com.rdcode.client.{normalized_id.lower()}",
        "T3CODE_DISABLE_AUTO_UPDATE": "1",
    }
    source_fingerprint = compute_rdcode_source_fingerprint(root)
    node_path = _command_path("node")
    pnpm_path = _command_path("pnpm")
    if node_path is None or pnpm_path is None:
        raise RdCodeInstanceError("node and pnpm must both be available on PATH")
    toolchain = {
        "node": _command_version(node_path, cwd=root),
        "nodePath": node_path,
        "pnpm": _command_version(pnpm_path, cwd=root),
        "pnpmPath": pnpm_path,
        "command": "pnpm build:desktop",
    }
    build_fingerprint = _json_fingerprint({
        "sourceFingerprint": source_fingerprint,
        "rendererEnvironment": renderer_env,
        "toolchain": toolchain,
    })
    return {
        "version": 1,
        "instanceId": normalized_id,
        "controlPlane": {
            "host": normalized_host,
            "port": ports["controlPlane"],
            "baseUrl": base_url,
            "clientPlanUrl": f"{base_url}/client-plan.json",
            "clientManifestUrl": f"{base_url}/client-manifest.json",
        },
        "ports": ports,
        "paths": paths,
        "rendererEnvironment": renderer_env,
        "desktopEnvironment": desktop_env,
        "build": {
            "sourceFingerprint": source_fingerprint,
            "fingerprint": build_fingerprint,
            "toolchain": toolchain,
        },
        "concurrency": {
            "mode": "exclusive-checkout",
            "lockPath": paths["checkoutLockPath"],
        },
        "tools": {
            "nodePath": node_path,
            "pnpmPath": pnpm_path,
            "pwshPath": _discover_pwsh(root),
        },
        "launch": {
            "readinessTimeoutSeconds": int(readiness_timeout_seconds),
            "exitAfterReadySeconds": int(exit_after_ready_seconds),
            "forceBuild": force_build,
        },
    }


def write_rdcode_instance_spec(spec: dict[str, Any]) -> Path:
    """Atomically persist an instance specification and return its path."""
    spec_path = Path(str(spec.get("paths", {}).get("specPath") or ""))
    if not spec_path.is_absolute():
        raise RdCodeInstanceError("paths.specPath must be absolute")
    instance_dir = Path(str(spec.get("paths", {}).get("instanceDir") or ""))
    if not _is_within(spec_path, instance_dir):
        raise RdCodeInstanceError("paths.specPath must remain inside paths.instanceDir")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = spec_path.with_name(
        f".{spec_path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    temporary_path.write_text(json.dumps(spec, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    try:
        os.chmod(temporary_path, 0o600)
    except OSError:
        pass
    try:
        with _SPEC_WRITE_LOCK:
            for attempt in range(20):
                try:
                    os.replace(temporary_path, spec_path)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    # Windows can transiently deny a replace while another
                    # process is opening or replacing the destination.
                    time.sleep(min(0.005 * (attempt + 1), 0.05))
    finally:
        temporary_path.unlink(missing_ok=True)
    return spec_path


def effective_rdcode_manifest_status(
    manifest: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str:
    """Return lease-aware status so a force-killed runner cannot remain ready."""
    status = str(manifest.get("status") or "unknown")
    if status not in _LEASED_INSTANCE_STATUSES:
        return status
    lease_expires_at = str(manifest.get("leaseExpiresAt") or "")
    try:
        expires = datetime.fromisoformat(lease_expires_at.replace("Z", "+00:00"))
    except ValueError:
        return "stale"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return status if expires > current else "stale"


def compute_rdcode_source_fingerprint(t3_root: str | Path) -> str:
    """Hash the checkout revision plus changed build inputs without build output."""
    root = Path(t3_root).resolve()
    git = shutil.which("git")
    if git and (root / ".git").exists():
        revision = _run_git(root, ["rev-parse", "HEAD"])
        changed = _run_git(root, ["diff", "--name-only", "-z", "HEAD", "--", *_BUILD_INPUTS])
        untracked = _run_git(root, ["ls-files", "--others", "--exclude-standard", "-z", "--", *_BUILD_INPUTS])
        if revision is not None and changed is not None and untracked is not None:
            paths = _decode_nul_paths(changed) | _decode_nul_paths(untracked)
            return _hash_checkout_files(root, revision.strip(), paths)
    return _hash_checkout_files(root, b"unversioned", _fallback_build_inputs(root))


def _validate_instance_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not _INSTANCE_ID_RE.fullmatch(normalized) or normalized in {".", ".."}:
        raise RdCodeInstanceError("instance_id must be 1-64 safe filename characters")
    return normalized


def _validate_loopback_host(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "localhost":
        return normalized
    try:
        address = ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        address = None
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_loopback:
        raise RdCodeInstanceError(
            "RD-Code desktop control plane must use localhost or an IPv4 loopback host"
        )
    return str(address)


def _validate_port(name: str, value: int) -> int:
    if isinstance(value, bool):
        raise RdCodeInstanceError(f"{name} must be an integer port")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise RdCodeInstanceError(f"{name} must be an integer port") from exc
    if port < 1 or port > 65535:
        raise RdCodeInstanceError(f"{name} must be between 1 and 65535")
    return port


def _build_instance_paths(t3_root: Path, instance_dir: Path) -> dict[str, str]:
    checkout_state_dir = t3_root / "apps" / "desktop" / ".electron-runtime" / "devframe-rdcode"
    paths = {
        "t3Root": str(t3_root),
        "runtimeRoot": str(instance_dir.parents[2]),
        "instanceDir": str(instance_dir),
        "appDataDir": str(instance_dir / "appdata"),
        "localAppDataDir": str(instance_dir / "local-appdata"),
        "t3Home": str(instance_dir / "t3-home"),
        "specPath": str(instance_dir / "instance-spec.json"),
        "manifestPath": str(instance_dir / "instance-manifest.json"),
        "buildStampPath": str(checkout_state_dir / "build-stamp.json"),
        "checkoutLockPath": str(checkout_state_dir / "checkout.lock"),
    }
    for key in ("appDataDir", "localAppDataDir", "t3Home", "specPath", "manifestPath"):
        if not _is_within(Path(paths[key]), instance_dir):
            raise RdCodeInstanceError(f"paths.{key} escapes the instance directory")
    return paths


def _build_renderer_environment(source: dict[str, Any], base_url: str) -> dict[str, str]:
    result = {
        str(key): str(value)
        for key, value in source.items()
        if str(key).startswith("VITE_DEVFRAME_") and value is not None
    }
    result["VITE_DEVFRAME_REALTIME_MODE"] = result.get("VITE_DEVFRAME_REALTIME_MODE", "polling")
    result["VITE_DEVFRAME_CLIENT_PLAN_URL"] = f"{base_url}/client-plan.json"
    result["VITE_DEVFRAME_CLIENT_MANIFEST_URL"] = f"{base_url}/client-manifest.json"
    return dict(sorted(result.items()))


def _loopback_base_url(host: str, port: int) -> str:
    rendered_host = f"[{host}]" if ":" in host else host
    return f"http://{rendered_host}:{port}"


def _json_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _command_path(command: str) -> str | None:
    executable = shutil.which(command)
    return str(Path(executable).resolve()) if executable else None


def _command_version(executable: str, *, cwd: Path) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=str(cwd),
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RdCodeInstanceError(
            f"cannot read pinned tool version for {executable!r} in {cwd}"
        ) from exc
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    if completed.returncode != 0 or not output or not output[0].strip():
        raise RdCodeInstanceError(
            f"cannot read pinned tool version for {executable!r} in {cwd}"
        )
    return output[0].strip()


def _discover_pwsh(t3_root: Path) -> str | None:
    for parent in [t3_root, *t3_root.parents]:
        for relative in (
            Path("powershell-portable") / "PowerShell" / "7" / "pwsh.exe",
            Path(".devframe-runtime") / "powershell-portable" / "PowerShell" / "7" / "pwsh.exe",
        ):
            candidate = parent / relative
            if candidate.is_file():
                return str(candidate.resolve())
    installed = shutil.which("pwsh")
    if installed:
        return str(Path(installed).resolve())
    return None


def _run_git(root: Path, args: list[str]) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _decode_nul_paths(raw: bytes) -> set[str]:
    return {part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\0") if part}


def _fallback_build_inputs(root: Path) -> set[str]:
    paths: set[str] = set()
    for relative in _BUILD_INPUTS:
        candidate = root / relative
        if candidate.is_file():
            paths.add(relative)
            continue
        if not candidate.is_dir():
            continue
        for path in candidate.rglob("*"):
            if path.is_file() and not (_IGNORED_BUILD_PARTS & set(path.relative_to(root).parts)):
                paths.add(path.relative_to(root).as_posix())
    return paths


def _hash_checkout_files(root: Path, revision: bytes, relative_paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    digest.update(revision)
    for relative in sorted(set(relative_paths)):
        normalized = relative.replace("\\", "/")
        digest.update(b"\0path\0" + normalized.encode("utf-8", errors="surrogateescape"))
        path = root / normalized
        if not path.is_file():
            digest.update(b"\0deleted")
            continue
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        normalized_path = os.path.normcase(os.path.abspath(os.fspath(path)))
        normalized_parent = os.path.normcase(os.path.abspath(os.fspath(parent)))
        return os.path.commonpath([normalized_path, normalized_parent]) == normalized_parent
    except (OSError, ValueError):
        return False
