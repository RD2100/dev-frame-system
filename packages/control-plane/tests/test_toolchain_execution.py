"""Production-shaped tests for the governed toolchain action path."""

from __future__ import annotations

import json
import hashlib
import os
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

from control_plane.cli.app import main
from control_plane.toolchain_execution import (
    _terminate_process_tree,
    execute_manifest_action,
)
from control_plane.run_index import build_run_index


def _write_manifest(project: Path) -> Path:
    manifest = project / "toolchain.json"
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('toolchain-marker.txt').write_text('ok', encoding='utf-8')",
    ]
    manifest.write_text(
        json.dumps(
            {
                "toolchain_id": "python-test",
                "compiler": "python",
                "working_directory": ".",
                "commands": {"build": command, "test": command},
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_toolchain_run_preview_is_explicit_and_has_no_runtime_write(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_manifest(project)
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "run",
            "--manifest",
            str(manifest),
            "--action",
            "test",
            "--project",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--format",
            "json",
        ],
    )

    assert main() == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "preview"
    assert output["execution"] == "explicit_only"
    assert not (project / "toolchain-marker.txt").exists()
    assert not runtime.exists()


def test_toolchain_run_cli_reaches_canonical_review_pending_path(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_manifest(project)
    runtime = tmp_path / "runtime"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "run",
            "--manifest",
            str(manifest),
            "--action",
            "test",
            "--project",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--timeout",
            "60",
            "--execute",
            "--format",
            "json",
        ],
    )

    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "passed"
    assert output["driver"] == "command"
    assert output["agents"][0]["changed_files"] == []
    assert (project / "toolchain-marker.txt").read_text(encoding="utf-8") == "ok"
    index = build_run_index(runtime)
    paired = [
        entry
        for entry in index["canonical_runs"]
        if {source["adapter_id"] for source in entry["provenance"]["sources"]}
        >= {"go_run", "team_events"}
    ]
    assert len(paired) == 1
    record = paired[0]["record"]
    assert record["domain"] == "code"
    assert record["profile"] == "go"
    assert record["outcome"] == "passed"
    assert record["review_state"] == "review_pending"
    assert record["acceptance_state"] == "review_pending"


def test_toolchain_run_rejects_runtime_inside_project(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_manifest(project)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "run",
            "--manifest",
            str(manifest),
            "--action",
            "test",
            "--project",
            str(project),
            "--runtime-dir",
            str(project / "runtime"),
            "--execute",
        ],
    )

    assert main() == 2

    assert "must stay outside the project" in capsys.readouterr().err
    assert not (project / "runtime").exists()
    assert not (project / "toolchain-marker.txt").exists()


def test_toolchain_execution_rejects_changed_manifest_bytes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_manifest(project)
    expected_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    manifest.write_text("toolchain_id: changed\n", encoding="utf-8")
    report = tmp_path / "ExecutionReport.md"

    assert execute_manifest_action(
        manifest,
        "test",
        project,
        expected_sha256=expected_sha256,
        report_path=report,
    ) == 2

    assert "manifest changed" in report.read_text(encoding="utf-8")
    assert not (project / "toolchain-marker.txt").exists()


def test_toolchain_execution_rejects_implicit_batch_shell(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    manifest = project / "toolchain.json"
    manifest.write_text(
        json.dumps(
            {
                "toolchain_id": "batch-shell",
                "commands": {
                    "build": ["build.cmd"],
                    "test": ["build.cmd", "test"],
                },
            }
        ),
        encoding="utf-8",
    )
    expected_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    report = tmp_path / "ExecutionReport.md"
    monkeypatch.setattr(
        "control_plane.toolchain_execution.shutil.which",
        lambda _command: "C:/tools/build.cmd",
    )

    assert execute_manifest_action(
        manifest,
        "test",
        project,
        expected_sha256=expected_sha256,
        report_path=report,
    ) == 2

    assert "batch-file executables" in report.read_text(encoding="utf-8")


def test_toolchain_run_binds_the_cli_approved_manifest_bytes(
    tmp_path, monkeypatch, capsys
):
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_manifest(project)
    approved_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    runtime = tmp_path / "runtime"
    import control_plane.go_dispatch as go_dispatch_module

    real_dispatch = go_dispatch_module.run_toolchain_dispatch

    def swap_then_dispatch(*args, **kwargs):
        swapped_command = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('swapped-marker.txt').write_text('swapped', encoding='utf-8')",
        ]
        manifest.write_text(
            json.dumps(
                {
                    "toolchain_id": "swapped",
                    "commands": {"build": swapped_command, "test": swapped_command},
                }
            ),
            encoding="utf-8",
        )
        return real_dispatch(*args, **kwargs)

    monkeypatch.setattr(go_dispatch_module, "run_toolchain_dispatch", swap_then_dispatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "run",
            "--manifest",
            str(manifest),
            "--action",
            "test",
            "--project",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--execute",
        ],
    )

    assert main() == 1

    capsys.readouterr()
    assert not (project / "swapped-marker.txt").exists()
    reports = list(runtime.rglob("ExecutionReport.md"))
    assert len(reports) == 1
    report_text = reports[0].read_text(encoding="utf-8")
    assert "manifest changed after the execution request was prepared" in report_text
    assert approved_sha256 in report_text
    index = build_run_index(runtime)
    paired = [
        entry
        for entry in index["canonical_runs"]
        if {source["adapter_id"] for source in entry["provenance"]["sources"]}
        >= {"go_run", "team_events"}
    ]
    assert paired[0]["record"]["outcome"] == "failed"


def test_toolchain_timeout_stops_descendant_processes(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    runtime = tmp_path / "runtime"
    child_script = (
        "import time; from pathlib import Path; time.sleep(2); "
        "Path('late-marker.txt').write_text('late', encoding='utf-8')"
    )
    parent_script = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        "time.sleep(10)"
    )
    command = [sys.executable, "-c", parent_script]
    manifest = project / "toolchain.json"
    manifest.write_text(
        json.dumps(
            {
                "toolchain_id": "timeout-tree",
                "commands": {"build": command, "test": command},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "run",
            "--manifest",
            str(manifest),
            "--action",
            "test",
            "--project",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--timeout",
            "1",
            "--execute",
        ],
    )

    assert main() == 1

    capsys.readouterr()
    time.sleep(2.5)
    assert not (project / "late-marker.txt").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group behavior")
def test_toolchain_timeout_stops_descendant_after_parent_exits(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    child_script = (
        "import time; from pathlib import Path; time.sleep(2); "
        "Path('late-marker.txt').write_text('late', encoding='utf-8')"
    )
    parent_script = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}])"
    )
    command = [sys.executable, "-c", parent_script]
    manifest = project / "toolchain.json"
    manifest.write_text(
        json.dumps(
            {
                "toolchain_id": "orphan-timeout-tree",
                "commands": {"build": command, "test": command},
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "ExecutionReport.md"

    assert execute_manifest_action(
        manifest,
        "test",
        project,
        expected_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        report_path=report,
        timeout_seconds=1,
    ) == 124

    time.sleep(2.5)
    assert not (project / "late-marker.txt").exists()


def test_posix_tree_termination_targets_group_after_leader_exit(monkeypatch):
    signals = []
    fake_os = SimpleNamespace(
        name="posix",
        killpg=lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )
    process = SimpleNamespace(pid=321, poll=lambda: 0, kill=lambda: None)
    monkeypatch.setattr("control_plane.toolchain_execution.os", fake_os)
    monkeypatch.setattr(
        "control_plane.toolchain_execution.signal",
        SimpleNamespace(SIGTERM=15, SIGKILL=9),
    )
    monkeypatch.setattr("control_plane.toolchain_execution.time.sleep", lambda _seconds: None)

    _terminate_process_tree(process)

    assert [sent_signal for _pid, sent_signal in signals] == [15, 0, 9]
