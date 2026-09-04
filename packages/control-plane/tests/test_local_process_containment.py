"""Real Windows process-tree checks for the provider-neutral Job boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from control_plane.local_process_containment import WindowsJob


def _pid_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    wait_timeout = 0x00000102
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
    finally:
        kernel32.CloseHandle(handle)


def _read_pid(path: Path) -> int | None:
    try:
        pid = int(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return pid if pid > 0 else None


def _cleanup_pid(pid: int) -> None:
    if not pid or not _pid_alive(pid):
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


@pytest.mark.skipif(os.name != "nt", reason="Windows Job real path")
def test_windows_job_assigns_before_resume_and_reaps_full_tree(tmp_path: Path):
    root_pid = tmp_path / "root.pid"
    child_pid = tmp_path / "child.pid"
    grandchild_pid = tmp_path / "grandchild.pid"
    late_marker = tmp_path / "late.txt"
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(1.0)\n"
        "Path(sys.argv[2]).write_text('late', encoding='utf-8')\n"
        "time.sleep(30.0)\n",
        encoding="utf-8",
    )
    child = tmp_path / "child.py"
    child.write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "subprocess.Popen([sys.executable, sys.argv[3], sys.argv[2], sys.argv[4]])\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(30.0)\n",
        encoding="utf-8",
    )
    root = tmp_path / "root.py"
    root.write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "subprocess.Popen([sys.executable, sys.argv[2], *sys.argv[3:]])\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(30.0)\n",
        encoding="utf-8",
    )

    job = WindowsJob()
    process: subprocess.Popen[bytes] | None = None
    pids: set[int] = set()
    closed = False
    try:
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | job.suspended_creation_flag()
        )
        process = subprocess.Popen(
            [
                sys.executable,
                str(root),
                str(root_pid),
                str(child),
                str(child_pid),
                str(grandchild_pid),
                str(grandchild),
                str(late_marker),
            ],
            cwd=str(tmp_path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        job.assign(process)
        job.resume(process)
        deadline = time.monotonic() + 5.0
        observed_pids: list[int | None] = []
        while time.monotonic() < deadline:
            observed_pids = [
                _read_pid(path) for path in (root_pid, child_pid, grandchild_pid)
            ]
            if all(pid is not None for pid in observed_pids):
                break
            time.sleep(0.01)
        assert all(pid is not None for pid in observed_pids)
        pids = {pid for pid in observed_pids if pid is not None}
        assert job.active_processes() >= 3
        assert job.close() is True
        closed = True
        process.wait(timeout=5.0)
        assert all(not _pid_alive(pid) for pid in pids)
        time.sleep(1.1)
        assert not late_marker.exists()
    finally:
        if not closed:
            job.close()
        if process is not None and process.poll() is None:
            _cleanup_pid(process.pid)
        for path in (root_pid, child_pid, grandchild_pid):
            pid = _read_pid(path)
            if pid is not None:
                pids.add(pid)
        for pid in pids:
            _cleanup_pid(pid)
