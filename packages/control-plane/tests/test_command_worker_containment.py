"""Real Windows containment checks for the provider-neutral CommandWorker."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from control_plane.cluster_run import _pid_alive
from control_plane.orchestrator import Orchestrator
from control_plane.project_contract import render_contract_markdown
from control_plane.worker import CommandWorker


def _ready_packet(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = tmp_path / "demo-project.md"
    contract_path.write_text(
        render_contract_markdown(
            "demo-project",
            "Build a working MVP prototype.",
        ),
        encoding="utf-8",
    )
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="Build a working MVP prototype.",
        operation="choose architecture direction",
    )
    return runtime_dir, Path(result.packet.packet_dir)


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


@pytest.mark.skipif(os.name != "nt", reason="covers the Windows reparented-child edge")
def test_command_worker_cancellation_reaps_reparented_grandchild(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    pids: dict[str, int] = {}

    def cleanup_processes() -> None:
        for pid in pids.values():
            _cleanup_pid(pid)

    request.addfinalizer(cleanup_processes)
    runtime_dir, packet_dir = _ready_packet(tmp_path)
    cancel_marker = tmp_path / "cancel-requested.json"
    root_pid_path = packet_dir / "worker-root.pid"
    grandchild_pid_path = packet_dir / "worker-grandchild.pid"
    child_done_path = packet_dir / "worker-child.done"
    child_script = tmp_path / "short-lived-child.py"
    child_script.write_text(
        "import pathlib, subprocess, sys\n"
        "grandchild = subprocess.Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(120)'],\n"
        "    stdin=subprocess.DEVNULL,\n"
        "    stdout=subprocess.DEVNULL,\n"
        "    stderr=subprocess.DEVNULL,\n"
        "    creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),\n"
        ")\n"
        "pathlib.Path(sys.argv[1]).write_text(str(grandchild.pid), encoding='utf-8')\n",
        encoding="utf-8",
    )
    root_script = tmp_path / "long-lived-root.py"
    root_script.write_text(
        "import os, pathlib, subprocess, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "subprocess.run([sys.executable, sys.argv[2], sys.argv[3]], check=True)\n"
        "pathlib.Path(sys.argv[4]).write_text('done', encoding='utf-8')\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10).run_packet,
            packet_dir,
            [
                sys.executable,
                str(root_script),
                str(root_pid_path),
                str(child_script),
                str(grandchild_pid_path),
                str(child_done_path),
            ],
            env_overrides={"DEVFRAME_CANCEL_MARKER": str(cancel_marker)},
        )
        deadline = time.monotonic() + 10
        while (
            not all(
                path.is_file()
                for path in (root_pid_path, grandchild_pid_path, child_done_path)
            )
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert child_done_path.is_file(), "short-lived child did not exit"
        pids["root"] = int(root_pid_path.read_text(encoding="utf-8"))
        pids["grandchild"] = int(grandchild_pid_path.read_text(encoding="utf-8"))
        assert _pid_alive(pids["root"])
        assert _pid_alive(pids["grandchild"])
        cancel_marker.write_text('{"requested": true}', encoding="utf-8")
        worker_result = future.result(timeout=15)

    assert not _pid_alive(pids["root"])
    assert not _pid_alive(pids["grandchild"])
    assert worker_result.summary.status == "cancelled"


@pytest.mark.skipif(os.name != "nt", reason="covers Windows pre-assignment cleanup")
def test_command_worker_assignment_failure_reaps_unassigned_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    import control_plane.worker as worker_module

    pids: dict[str, int] = {}
    request.addfinalizer(lambda: _cleanup_pid(pids.get("root", 0)))

    class FailingAssignmentJob:
        def suspended_creation_flag(self) -> int:
            return 0x00000004

        def assign(self, process: subprocess.Popen[str]) -> None:
            pids["root"] = process.pid
            raise OSError("synthetic assignment failure")

        def resume(self, process: subprocess.Popen[str]) -> None:
            raise AssertionError("resume must not run after failed assignment")

        def close(self) -> bool:
            return True

    monkeypatch.setattr(worker_module, "WindowsJob", FailingAssignmentJob)
    runtime_dir, packet_dir = _ready_packet(tmp_path)

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(
        packet_dir,
        [sys.executable, "-c", "import time; time.sleep(120)"],
    )

    assert worker_result.summary.status == "failed"
    assert pids["root"] > 0
    assert not _pid_alive(pids["root"])


@pytest.mark.skipif(os.name != "nt", reason="covers Windows cleanup truth")
def test_command_worker_job_cleanup_failure_cannot_report_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import control_plane.worker as worker_module

    class FailedCleanupJob:
        def suspended_creation_flag(self) -> int:
            return 0

        def assign(self, process: subprocess.Popen[str]) -> None:
            return None

        def resume(self, process: subprocess.Popen[str]) -> None:
            return None

        def close(self) -> bool:
            return False

    monkeypatch.setattr(worker_module, "WindowsJob", FailedCleanupJob)
    runtime_dir, packet_dir = _ready_packet(tmp_path)
    command = [
        sys.executable,
        "-c",
        (
            "import os, pathlib; "
            "pathlib.Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
            "'## ExecutionReport: command\\n\\n- **Status**: pass\\n', "
            "encoding='utf-8')"
        ),
    ]

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(
        packet_dir,
        command,
    )

    assert worker_result.summary.status == "failed"
    assert "containment cleanup failed" in Path(worker_result.report_path).read_text(
        encoding="utf-8"
    )
    report_text = Path(worker_result.report_path).read_text(encoding="utf-8")
    assert "## Worker-provided partial report" in report_text
    assert "- **Status**: pass" in report_text


@pytest.mark.skipif(os.name != "nt", reason="covers thrown Windows cleanup")
def test_command_worker_job_cleanup_exception_is_sanitized_and_reaps_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    import json

    import control_plane.worker as worker_module

    pids: dict[str, int] = {}

    def cleanup_processes() -> None:
        for pid in pids.values():
            _cleanup_pid(pid)

    class ThrowingCleanupJob:
        def suspended_creation_flag(self) -> int:
            return 0

        def assign(self, process: subprocess.Popen[str]) -> None:
            return None

        def resume(self, process: subprocess.Popen[str]) -> None:
            return None

        def close(self) -> bool:
            raise RuntimeError("SECRET_CLEANUP_DETAIL")

    request.addfinalizer(cleanup_processes)
    monkeypatch.setattr(worker_module, "WindowsJob", ThrowingCleanupJob)
    runtime_dir, packet_dir = _ready_packet(tmp_path)
    cancel_marker = tmp_path / "cancel-requested.json"
    pid_path = packet_dir / "worker-pids.json"
    script_path = tmp_path / "worker-tree.py"
    script_path.write_text(
        "import json, os, pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "pathlib.Path(os.environ['RDGOAL_REPORT_PATH']).write_text(\n"
        "    '## ExecutionReport: partial\\n\\n- **Status**: pass\\n', encoding='utf-8'\n"
        ")\n"
        "pathlib.Path(sys.argv[1]).write_text(\n"
        "    json.dumps({'root': os.getpid(), 'child': child.pid}), encoding='utf-8'\n"
        ")\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10).run_packet,
            packet_dir,
            [sys.executable, str(script_path), str(pid_path)],
            env_overrides={"DEVFRAME_CANCEL_MARKER": str(cancel_marker)},
        )
        deadline = time.monotonic() + 10
        while not pid_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pid_path.is_file(), "worker tree did not start"
        pids.update(json.loads(pid_path.read_text(encoding="utf-8")))
        assert all(_pid_alive(pid) for pid in pids.values())
        cancel_marker.write_text('{"requested": true}', encoding="utf-8")
        worker_result = future.result(timeout=15)

    report_text = Path(worker_result.report_path).read_text(encoding="utf-8")
    output_text = (packet_dir / "worker-output.txt").read_text(encoding="utf-8")
    assert worker_result.summary.status == "failed"
    assert "containment cleanup failed" in report_text
    assert "SECRET_CLEANUP_DETAIL" not in report_text
    assert "SECRET_CLEANUP_DETAIL" not in output_text
    assert all(not _pid_alive(pid) for pid in pids.values())


@pytest.mark.skipif(os.name != "nt", reason="covers assigned resume failure cleanup")
def test_command_worker_resume_failure_reaps_assigned_suspended_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    import control_plane.worker as worker_module

    real_job = worker_module.WindowsJob
    pids: dict[str, int] = {}
    request.addfinalizer(lambda: _cleanup_pid(pids.get("root", 0)))

    class FailingResumeJob:
        def __init__(self) -> None:
            self.inner = real_job()

        def suspended_creation_flag(self) -> int:
            return self.inner.suspended_creation_flag()

        def assign(self, process: subprocess.Popen[str]) -> None:
            self.inner.assign(process)
            pids["root"] = process.pid

        def resume(self, process: subprocess.Popen[str]) -> None:
            raise OSError("synthetic resume failure")

        def close(self) -> bool:
            return self.inner.close()

    monkeypatch.setattr(worker_module, "WindowsJob", FailingResumeJob)
    runtime_dir, packet_dir = _ready_packet(tmp_path)

    worker_result = CommandWorker(runtime_dir=runtime_dir).run_packet(
        packet_dir,
        [sys.executable, "-c", "import time; time.sleep(120)"],
    )

    assert worker_result.summary.status == "failed"
    assert pids["root"] > 0
    assert not _pid_alive(pids["root"])


@pytest.mark.skipif(os.name != "nt", reason="covers real Windows timeout cleanup")
def test_command_worker_timeout_reaps_real_process_tree(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    import json

    pids: dict[str, int] = {}

    def cleanup_processes() -> None:
        for pid in pids.values():
            _cleanup_pid(pid)

    request.addfinalizer(cleanup_processes)
    runtime_dir, packet_dir = _ready_packet(tmp_path)
    pid_path = packet_dir / "timeout-pids.json"
    script_path = tmp_path / "timeout-tree.py"
    script_path.write_text(
        "import json, os, pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "pathlib.Path(os.environ['RDGOAL_REPORT_PATH']).write_text(\n"
        "    '## ExecutionReport: partial\\n\\n- **Status**: pass\\n', encoding='utf-8'\n"
        ")\n"
        "pathlib.Path(sys.argv[1]).write_text(\n"
        "    json.dumps({'root': os.getpid(), 'child': child.pid}), encoding='utf-8'\n"
        ")\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )

    worker_result = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=1).run_packet(
        packet_dir,
        [sys.executable, str(script_path), str(pid_path)],
    )

    assert pid_path.is_file(), "timeout tree did not start"
    pids.update(json.loads(pid_path.read_text(encoding="utf-8")))
    assert worker_result.summary.status == "failed"
    assert "TIMEOUT after 1 seconds" in (packet_dir / "worker-output.txt").read_text(
        encoding="utf-8"
    )
    report_text = Path(worker_result.report_path).read_text(encoding="utf-8")
    assert "## Worker-provided partial report" in report_text
    assert "- **Status**: pass" in report_text
    assert all(not _pid_alive(pid) for pid in pids.values())


@pytest.mark.skipif(os.name != "nt", reason="covers runtime exception cleanup")
def test_command_worker_runtime_exception_preserves_primary_and_reaps_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    import json

    import control_plane.worker as worker_module

    pids: dict[str, int] = {}

    def cleanup_processes() -> None:
        for pid in pids.values():
            _cleanup_pid(pid)

    request.addfinalizer(cleanup_processes)
    runtime_dir, packet_dir = _ready_packet(tmp_path)
    pid_path = packet_dir / "runtime-error-pids.json"
    script_path = tmp_path / "runtime-error-tree.py"
    script_path.write_text(
        "import json, os, pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(\n"
        "    json.dumps({'root': os.getpid(), 'child': child.pid}), encoding='utf-8'\n"
        ")\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    real_popen = subprocess.Popen

    class ThrowingCleanupJob:
        def suspended_creation_flag(self) -> int:
            return 0

        def assign(self, process: subprocess.Popen[str]) -> None:
            return None

        def resume(self, process: subprocess.Popen[str]) -> None:
            return None

        def close(self) -> bool:
            raise RuntimeError("SECRET_CLEANUP_DETAIL")

    class FaultingCommunicateProcess:
        def __init__(self, inner: subprocess.Popen[str]) -> None:
            self.inner = inner
            self.faulted = False

        def __getattr__(self, name: str):
            return getattr(self.inner, name)

        def communicate(self, *args, **kwargs):
            if pid_path.is_file() and not self.faulted:
                self.faulted = True
                raise RuntimeError("SECRET_COMMUNICATE_DETAIL")
            return self.inner.communicate(*args, **kwargs)

    def faulting_popen(*args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        if isinstance(command, list) and command and command[0] == "taskkill":
            return real_popen(*args, **kwargs)
        return FaultingCommunicateProcess(real_popen(*args, **kwargs))

    monkeypatch.setattr(worker_module, "WindowsJob", ThrowingCleanupJob)
    monkeypatch.setattr(worker_module.subprocess, "Popen", faulting_popen)

    worker_result = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10).run_packet(
        packet_dir,
        [sys.executable, str(script_path), str(pid_path)],
    )

    assert pid_path.is_file(), "runtime-error tree did not start"
    pids.update(json.loads(pid_path.read_text(encoding="utf-8")))
    report_text = Path(worker_result.report_path).read_text(encoding="utf-8")
    output_text = (packet_dir / "worker-output.txt").read_text(encoding="utf-8")
    assert worker_result.summary.status == "failed"
    assert "RuntimeError" in report_text
    assert "containment cleanup failed" in report_text
    assert "SECRET_COMMUNICATE_DETAIL" not in report_text
    assert "SECRET_COMMUNICATE_DETAIL" not in output_text
    assert "SECRET_CLEANUP_DETAIL" not in report_text
    assert "SECRET_CLEANUP_DETAIL" not in output_text
    assert all(not _pid_alive(pid) for pid in pids.values())


@pytest.mark.skipif(os.name != "nt", reason="covers bounded Windows fallback")
def test_command_worker_taskkill_timeout_falls_back_to_root_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import control_plane.worker as worker_module

    class SyntheticProcess:
        pid = 424242

        def __init__(self) -> None:
            self.killed = False

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float) -> int:
            return 1

    def timeout_taskkill(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=5.0)

    process = SyntheticProcess()
    monkeypatch.setattr(
        worker_module,
        "_windows_descendant_process_ids",
        lambda pid, **kwargs: ([], True),
    )
    monkeypatch.setattr(worker_module.subprocess, "run", timeout_taskkill)

    cleanup_ok = worker_module._terminate_command_process_tree(process)

    assert process.killed is True
    assert cleanup_ok is False


def test_bounded_descendant_walk_rejects_cycles_and_overflow() -> None:
    from control_plane.worker import _bounded_descendant_ids

    cycle_descendants, cycle_complete = _bounded_descendant_ids(
        {1: [2], 2: [3], 3: [2]},
        1,
        deadline=time.monotonic() + 1,
        limit=10,
    )
    overflow_descendants, overflow_complete = _bounded_descendant_ids(
        {1: [2, 3, 4, 5]},
        1,
        deadline=time.monotonic() + 1,
        limit=2,
    )

    assert cycle_descendants == [2, 3]
    assert cycle_complete is False
    assert len(overflow_descendants) == 2
    assert overflow_complete is False
