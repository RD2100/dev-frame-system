from __future__ import annotations

import base64
import csv
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from control_plane.orchestrator import Orchestrator
from control_plane.project_contract import render_contract_markdown
from control_plane.worker import CommandWorker, _resolve_command


def _prepared_packet(tmp_path: Path) -> tuple[Path, Path, str]:
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    contract_path = tmp_path / "project.md"
    contract_path.write_text(
        render_contract_markdown("worker-process-control", "Run a bounded worker."),
        encoding="utf-8",
    )
    orchestrator = Orchestrator(runtime_dir=runtime_dir, repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    dispatch = orchestrator.dispatch(
        project_id="worker-process-control",
        requirement="Run a bounded worker.",
        operation="implement bounded worker behavior",
    )
    assert dispatch.packet is not None
    return project_root, runtime_dir, dispatch.packet.packet_dir


def _pid_is_running(pid: int) -> bool:
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        return any(
            len(row) > 1 and row[1] == str(pid)
            for row in csv.reader(io.StringIO(completed.stdout))
        )
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stop_pid_tree(pid: int) -> None:
    if not _pid_is_running(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _wait_until_stopped(*pids: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_pid_is_running(pid) for pid in pids):
            return True
        time.sleep(0.05)
    return not any(_pid_is_running(pid) for pid in pids)


def _process_tree_command(pid_path: Path) -> list[str]:
    child_code = "import time; time.sleep(60)"
    parent_code = (
        "import json, os, subprocess, sys, time; "
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "open(sys.argv[1], 'w', encoding='utf-8').write("
        "json.dumps({'parent': os.getpid(), 'child': child.pid})); "
        "time.sleep(60)"
    )
    return [sys.executable, "-c", parent_code, str(pid_path)]


def _write_passing_python_worker(script_path: Path, label: str) -> None:
    script_path.write_text(
        "import os, pathlib, sys\n"
        "report = (\n"
        f"    '## ExecutionReport: {label}\\n\\n'\n"
        "    '- **Status**: pass\\n'\n"
        "    '- **Review Status**: draft\\n'\n"
        f"    '- **Summary**: {label} completed.\\n'\n"
        "    '- **Changed Files**:\\n- (none)\\n'\n"
        f"    '- **Evidence**: {label} fixture.\\n'\n"
        ")\n"
        "pathlib.Path(os.environ['RDGOAL_REPORT_PATH']).write_text(report, encoding='utf-8')\n"
        f"print('{label}-STDOUT:' + sys.argv[1])\n"
        f"print('{label}-STDERR:' + sys.argv[1], file=sys.stderr)\n",
        encoding="utf-8",
    )


def test_command_worker_timeout_stops_only_its_owned_process_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, runtime_dir, packet_dir = _prepared_packet(tmp_path)
    pid_path = tmp_path / "owned-processes.json"
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    owned_pids: list[int] = []
    cleanup_seen_before_ingest: list[bool] = []
    try:
        worker = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=1)
        original_ingest = worker.store.ingest_report

        def ingest_after_cleanup(packet_path: str | Path, report_path: str | Path):
            owned = json.loads(pid_path.read_text(encoding="utf-8"))
            cleanup_seen_before_ingest.append(
                _wait_until_stopped(int(owned["parent"]), int(owned["child"]))
            )
            return original_ingest(packet_path, report_path)

        monkeypatch.setattr(worker.store, "ingest_report", ingest_after_cleanup)
        if os.name != "nt":
            monkeypatch.setattr(
                "control_plane.worker.subprocess.run",
                lambda *args, **kwargs: pytest.fail(
                    f"non-Windows timeout cleanup invoked subprocess.run: {args!r}"
                ),
            )

        result = worker.run_packet(
            packet_dir,
            _process_tree_command(pid_path),
            cwd=project_root,
        )
        owned = json.loads(pid_path.read_text(encoding="utf-8"))
        owned_pids = [int(owned["parent"]), int(owned["child"])]

        assert result.summary.status == "failed"
        assert "worker command timed out" in Path(result.report_path).read_text(encoding="utf-8")
        assert cleanup_seen_before_ingest == [True]
        assert _wait_until_stopped(*owned_pids)
        assert unrelated.poll() is None
    finally:
        for pid in owned_pids:
            _stop_pid_tree(pid)
        if unrelated.poll() is None:
            unrelated.terminate()
            try:
                unrelated.wait(timeout=5)
            except subprocess.TimeoutExpired:
                unrelated.kill()
                unrelated.wait(timeout=5)


def test_command_worker_normal_root_exit_cleans_descendant_before_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, runtime_dir, packet_dir = _prepared_packet(tmp_path)
    pid_path = tmp_path / "parent-exit-processes.json"
    child_code = "import time; time.sleep(60)"
    parent_code = (
        "import json, os, pathlib, subprocess, sys; "
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "pathlib.Path(sys.argv[1]).write_text("
        "json.dumps({'parent': os.getpid(), 'child': child.pid}), encoding='utf-8'); "
        "pathlib.Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport: parent exit\\n\\n- **Status**: pass\\n"
        "- **Review Status**: draft\\n- **Changed Files**:\\n- (none)\\n"
        "- **Evidence**: parent exited zero.\\n', encoding='utf-8')"
    )
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    owned_pids: list[int] = []
    cleanup_seen_before_ingest: list[bool] = []
    try:
        worker = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10)
        original_ingest = worker.store.ingest_report

        def ingest_after_cleanup(packet_path: str | Path, report_path: str | Path):
            owned = json.loads(pid_path.read_text(encoding="utf-8"))
            cleanup_seen_before_ingest.append(
                _wait_until_stopped(int(owned["parent"]), int(owned["child"]))
            )
            return original_ingest(packet_path, report_path)

        monkeypatch.setattr(worker.store, "ingest_report", ingest_after_cleanup)
        result = worker.run_packet(
            packet_dir,
            [sys.executable, "-c", parent_code, str(pid_path)],
            cwd=project_root,
        )
        owned = json.loads(pid_path.read_text(encoding="utf-8"))
        owned_pids = [int(owned["parent"]), int(owned["child"])]
        report = Path(result.report_path).read_text(encoding="utf-8")

        assert result.summary.status == "failed"
        assert "owned descendant" in report
        assert cleanup_seen_before_ingest == [True]
        assert _wait_until_stopped(*owned_pids)
        assert unrelated.poll() is None
    finally:
        for pid in owned_pids:
            _stop_pid_tree(pid)
        if unrelated.poll() is None:
            unrelated.terminate()
            try:
                unrelated.wait(timeout=5)
            except subprocess.TimeoutExpired:
                unrelated.kill()
                unrelated.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="PowerShell shim behavior is Windows-specific")
def test_command_worker_runs_powershell_shim_with_explicit_interpreter(tmp_path: Path) -> None:
    project_root, runtime_dir, packet_dir = _prepared_packet(tmp_path)
    script_path = tmp_path / "benign-worker.ps1"
    script_path.write_text(
        "param([string]$Empty, [string]$Space, [string]$Quote, [string]$Meta)\n"
        "$report = \"## ExecutionReport: powershell shim`n`n"
        "- **Status**: pass`n"
        "- **Review Status**: draft`n"
        "- **Summary**: PowerShell shim completed.`n"
        "- **Changed Files**:`n- (none)`n"
        "- **Evidence**: benign PowerShell fixture.`n\"\n"
        "[System.IO.File]::WriteAllText($env:RDGOAL_REPORT_PATH, $report, "
        "[System.Text.UTF8Encoding]::new($false))\n"
        "function Encode([string]$Value) { "
        "return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Value)) }\n"
        "$encoded = \"$(Encode $Empty),$(Encode $Space),$(Encode $Quote),$(Encode $Meta)\"\n"
        "[Console]::Out.WriteLine(\"PS1-ARGS:$encoded\")\n"
        "[Console]::Error.WriteLine(\"PS1-STDERR:token-safe\")\n"
        "exit 0\n",
        encoding="utf-8",
    )

    arguments = ["", "space value", 'quote"value', "&|<>^%!"]
    encoded_arguments = ",".join(
        base64.b64encode(value.encode("utf-8")).decode("ascii") for value in arguments
    )
    command = [str(script_path), *arguments]
    resolved = _resolve_command(command)
    result = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10).run_packet(
        packet_dir,
        command,
        cwd=project_root,
    )
    output = (Path(packet_dir) / "worker-output.txt").read_text(encoding="utf-8")

    assert resolved[:7] == [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
    ]
    assert result.summary.status == "passed"
    assert output == (
        "STDOUT\n"
        f"PS1-ARGS:{encoded_arguments}\n\n\n"
        "STDERR\n"
        "PS1-STDERR:token-safe\n\n"
    )


@pytest.mark.skipif(os.name != "nt", reason="batch rejection is Windows-specific")
@pytest.mark.parametrize(
    ("extension", "argument"),
    [
        (".cmd", ""),
        (".cmd", "space value"),
        (".cmd", 'quote"value'),
        (".cmd", "&|<>^%!"),
        (".bat", "batch value"),
    ],
)
def test_command_worker_rejects_batch_scripts_without_reinterpreting_arguments(
    tmp_path: Path, extension: str, argument: str
) -> None:
    project_root, runtime_dir, packet_dir = _prepared_packet(tmp_path)
    marker_path = tmp_path / "batch-ran.txt"
    script_path = tmp_path / f"unsafe-worker{extension}"
    script_path.write_text(
        "@echo off\n"
        f'echo ran>"{marker_path}"\n'
        "exit /b %ERRORLEVEL%\n",
        encoding="utf-8",
    )

    result = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10).run_packet(
        packet_dir,
        [str(script_path), argument],
        cwd=project_root,
    )
    report = Path(result.report_path).read_text(encoding="utf-8")
    output = (Path(packet_dir) / "worker-output.txt").read_text(encoding="utf-8")

    assert result.summary.status == "failed"
    assert "Windows batch scripts are not supported" in report
    assert "FAILED TO START" in output
    assert not marker_path.exists()


def test_command_worker_keeps_normal_executable_behavior(tmp_path: Path) -> None:
    project_root, runtime_dir, packet_dir = _prepared_packet(tmp_path)
    python_worker_path = tmp_path / "normal-worker.py"
    _write_passing_python_worker(python_worker_path, "NORMAL")
    command = [sys.executable, str(python_worker_path), "exact-value"]

    resolved = _resolve_command(command)
    result = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10).run_packet(
        packet_dir,
        command,
        cwd=project_root,
    )
    output = (Path(packet_dir) / "worker-output.txt").read_text(encoding="utf-8")

    assert resolved == [str(Path(sys.executable)), str(python_worker_path), "exact-value"]
    assert result.summary.status == "passed"
    assert "NORMAL-STDOUT:exact-value" in output
    assert "NORMAL-STDERR:exact-value" in output


def test_command_worker_missing_executable_fails_closed(tmp_path: Path) -> None:
    project_root, runtime_dir, packet_dir = _prepared_packet(tmp_path)

    result = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=10).run_packet(
        packet_dir,
        ["definitely-missing-worker-process-control-command"],
        cwd=project_root,
    )
    report = Path(result.report_path).read_text(encoding="utf-8")
    output = (Path(packet_dir) / "worker-output.txt").read_text(encoding="utf-8")

    assert result.summary.status == "failed"
    assert "worker command could not start" in report
    assert "FAILED TO START" in output


def test_command_worker_cleanup_failure_is_explicit_and_not_fake_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, runtime_dir, packet_dir = _prepared_packet(tmp_path)
    pid_path = tmp_path / "cleanup-failure-processes.json"
    owned_pids: list[int] = []
    termination_attempts: list[object] = []

    if os.name == "nt":
        def fail_job_termination(job):
            termination_attempts.append("TerminateJobObject")
            return False, "simulated Job Object termination denial"

        monkeypatch.setattr(
            "control_plane.worker._WindowsJob.terminate", fail_job_termination
        )
    else:

        def fail_killpg(process_group_id: int, sig: int) -> None:
            termination_attempts.append((process_group_id, sig))
            raise PermissionError("simulated process-group cleanup denial")

        monkeypatch.setattr("control_plane.worker.os.killpg", fail_killpg)

    try:
        result = CommandWorker(runtime_dir=runtime_dir, timeout_seconds=1).run_packet(
            packet_dir,
            _process_tree_command(pid_path),
            cwd=project_root,
        )
        owned = json.loads(pid_path.read_text(encoding="utf-8"))
        owned_pids = [int(owned["parent"]), int(owned["child"])]
        report = Path(result.report_path).read_text(encoding="utf-8")
        output = (Path(packet_dir) / "worker-output.txt").read_text(encoding="utf-8")

        assert termination_attempts
        if os.name == "nt":
            assert termination_attempts == ["TerminateJobObject"]
            assert _wait_until_stopped(*owned_pids)
        else:
            assert termination_attempts == [(owned_pids[0], signal.SIGTERM)]
            assert _pid_is_running(owned_pids[1])
        assert result.summary.status == "failed"
        assert "process tree cleanup failed" in report
        assert "PROCESS TREE CLEANUP: FAILED" in output
        assert "PROCESS TREE CLEANUP: confirmed" not in output
    finally:
        for pid in owned_pids:
            _stop_pid_tree(pid)
        assert _wait_until_stopped(*owned_pids)
