"""Production-path tests for the offline adapter conformance command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from control_plane import adapter_conformance
from control_plane.adapter_conformance import verify_adapter_conformance
from control_plane.cli.app import main
from control_plane.go_dispatch import run_go_dispatch


def _passing_command() -> list[str]:
    report = (
        "## ExecutionReport\n\n"
        "- **Status**: pass\n"
        "- **Review Status**: draft\n"
        "- **Changed Files**:\n"
        "- (none)\n"
        "- **Evidence**: adapter conformance fixture\n"
    )
    script = (
        "import os; from pathlib import Path; "
        f"Path(os.environ['RDGOAL_REPORT_PATH']).write_text({report!r}, encoding='utf-8')"
    )
    return [sys.executable, "-c", script]


def _run_fixture(tmp_path: Path, name: str, *, passing: bool) -> Path:
    root = tmp_path / name
    project = root / "project"
    project.mkdir(parents=True)
    (project / "target.py").write_text("value = 0\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "config", "user.email", "adapter@test.local"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "config", "user.name", "adapter-test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-q", "-m", "fixture"], check=True)
    command = _passing_command() if passing else [sys.executable, "-c", "raise SystemExit(3)"]
    result = run_go_dispatch(
        project,
        "adapter conformance fixture",
        runtime_dir=root / "runtime",
        agents=1,
        targets=["target.py"],
        execute=True,
        worker_command=command,
        driver="command",
        timeout_seconds=60,
    )
    assert result.status == ("passed" if passing else "failed")
    return root / "runtime"


def test_adapter_conformance_compares_real_canonical_records(tmp_path):
    reference_runtime = _run_fixture(tmp_path, "reference", passing=True)
    candidate_runtime = _run_fixture(tmp_path, "candidate", passing=True)

    result = verify_adapter_conformance(reference_runtime, candidate_runtime)

    assert result["status"] == "pass", result["errors"]
    assert result["reference"]["drivers"] == ["command"]
    assert result["candidate"]["drivers"] == ["command"]


def test_adapter_conformance_rejects_divergent_canonical_records(tmp_path):
    reference_runtime = _run_fixture(tmp_path, "reference", passing=True)
    candidate_runtime = _run_fixture(tmp_path, "candidate", passing=False)

    result = verify_adapter_conformance(reference_runtime, candidate_runtime)

    assert result["status"] == "fail"
    assert "canonical governance fields differ" in result["errors"]


def test_adapter_conformance_rejects_non_code_profile(monkeypatch, tmp_path):
    entry = {
        "record": {
            "run_id": "paper-run",
            "domain": "paper",
            "profile": "paper",
            "outcome": "passed",
            "review_state": "review_pending",
            "gate_state": "not_evaluated",
            "acceptance_state": "review_pending",
            "domain_refs": {
                "source_domain_refs": {"go_run": [{"driver": "command"}]}
            },
        },
        "provenance": {
            "sources": [{"adapter_id": "go_run"}, {"adapter_id": "team_events"}]
        },
    }
    monkeypatch.setattr(
        adapter_conformance,
        "_select_canonical_go_record",
        lambda _runtime, _run_id: (entry, []),
    )

    result = verify_adapter_conformance(tmp_path / "reference", tmp_path / "candidate")

    assert result["status"] == "fail"
    assert "reference: canonical record domain must be code" in result["errors"]
    assert "candidate: canonical record profile must be go" in result["errors"]


def test_adapter_conformance_cli_is_read_only_and_json(tmp_path, monkeypatch, capsys):
    reference_runtime = _run_fixture(tmp_path, "reference", passing=True)
    candidate_runtime = _run_fixture(tmp_path, "candidate", passing=True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "adapter",
            "verify",
            "--reference-runtime",
            str(reference_runtime),
            "--candidate-runtime",
            str(candidate_runtime),
            "--format",
            "json",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert '"status": "pass"' in output
    assert not (reference_runtime / "adapter-conformance.json").exists()
    assert not (candidate_runtime / "adapter-conformance.json").exists()
