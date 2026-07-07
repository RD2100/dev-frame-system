import json
import os
import subprocess
import sys

import pytest
from jsonschema.validators import validator_for

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import go_evidence

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _write_yaml(path: str, data: dict) -> None:
    try:
        import yaml

        content = yaml.safe_dump(data)
    except ImportError:
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f'  - "{item}"')
            else:
                lines.append(f'{key}: "{value}"')
        content = "\n".join(lines) + "\n"
    _write(path, content)


def _write_json(path: str, data: dict) -> None:
    _write(path, json.dumps(data, indent=2) + "\n")


def _schema_validator(path: str):
    with open(os.path.join(REPO_ROOT, path), "r", encoding="utf-8-sig") as fh:
        schema = json.load(fh)
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _setup_minimal_evidence(tmp_path: str, review_overrides: dict = None) -> str:
    review = {
        "reviewer_role": "reviewer",
        "reviewer_id": "reviewer-1",
        "executor_id": "executor-1",
        "verdict": "pass",
        "reviewed_inputs": ["diff.patch", "test-output.md", "safety-report.json", "chain-evidence.json"],
        "findings": [],
    }
    if review_overrides:
        review.update(review_overrides)

    _write(os.path.join(tmp_path, "diff.patch"), "")
    _write(os.path.join(tmp_path, "test-output.md"), "")
    _write_json(os.path.join(tmp_path, "safety-report.json"), {"generated_at": "2026-06-24T00:00:00+00:00", "producer": "ai_guard.py", "command": "noop", "exit_code": 0, "stdout": ""})
    _write_json(os.path.join(tmp_path, "chain-evidence.json"), {})
    _write(os.path.join(tmp_path, "review.md"), "")
    _write_yaml(os.path.join(tmp_path, "review.yaml"), review)
    return tmp_path


def test_missing_artifacts_blocked(tmp_path):
    evidence_dir = os.path.join(str(tmp_path), "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 1
    with open(os.path.join(evidence_dir, "failure-record.json"), "r", encoding="utf-8") as fh:
        failure = json.load(fh)
    with open(os.path.join(evidence_dir, "final-verdict.json"), "r", encoding="utf-8") as fh:
        final_verdict = json.load(fh)
    _schema_validator("schemas/agent-runtime/failure-record.schema.json").validate(failure)
    _schema_validator("schemas/agent-runtime/final-verdict.schema.json").validate(final_verdict)
    assert failure["source_contract"] == "EvidenceManifest"
    assert final_verdict["final_state"] == "blocked"


def test_executor_self_review_blocked(tmp_path):
    evidence_dir = _setup_minimal_evidence(str(tmp_path), {"reviewer_role": "executor"})
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 1


def test_same_reviewer_and_executor_id_blocked(tmp_path):
    evidence_dir = _setup_minimal_evidence(
        str(tmp_path),
        {"reviewer_id": "executor-1", "executor_id": "executor-1"},
    )
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 1
    failure_record = os.path.join(evidence_dir, "failure-record.json")
    final_verdict = os.path.join(evidence_dir, "final-verdict.json")
    assert os.path.exists(failure_record)
    assert os.path.exists(final_verdict)
    with open(failure_record, "r", encoding="utf-8") as fh:
        failure = json.load(fh)
    _schema_validator("schemas/agent-runtime/failure-record.schema.json").validate(failure)
    assert failure["status"] == "blocked"
    assert "reviewer_id must differ from executor_id" in failure["reason"]
    with open(final_verdict, "r", encoding="utf-8") as fh:
        verdict = json.load(fh)
    assert verdict["final_state"] == "blocked"


@pytest.mark.parametrize("reviewer_role", ["executor ", " worker ", "Coder ", "fixer ", "FIXER"])
def test_reviewer_role_whitespace_and_case_self_review_blocked(tmp_path, reviewer_role):
    evidence_dir = _setup_minimal_evidence(str(tmp_path), {"reviewer_role": reviewer_role})
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 1
    with open(os.path.join(evidence_dir, "final-verdict.json"), "r", encoding="utf-8") as fh:
        final_verdict = json.load(fh)
    assert final_verdict["final_state"] == "blocked"


def test_open_p0_finding_blocked(tmp_path):
    evidence_dir = _setup_minimal_evidence(
        str(tmp_path),
        {
            "reviewer_role": "reviewer",
            "findings": [{"id": "f1", "severity": "P0", "status": "open", "title": "test"}],
        },
    )
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 1


def test_init_creates_chain_evidence(tmp_path):
    run_dir = os.path.join(str(tmp_path), "run")
    rc = go_evidence.main([
        "init",
        run_dir,
        "--run-id", "run-1",
        "--executor-id", "executor-1",
        "--mode", "auto_execute",
        "--planner", "planner-1",
        "--task", "docs/task.md",
    ])
    assert rc == 0
    evidence_path = os.path.join(run_dir, "chain-evidence.json")
    assert os.path.exists(evidence_path)
    with open(evidence_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["run_id"] == "run-1"
    assert data["executor_id"] == "executor-1"
    assert data["mode"] == "auto_execute"
    assert data["planner"] == "planner-1"
    assert data["task"] == "docs/task.md"
    assert isinstance(data["evidence_files"], list)
    assert data["evidence_files"]
    assert set(data["evidence_files"]) == set(go_evidence.FULL_EVIDENCE_FILES)
    assert "final-report.md" in data["evidence_files"]
    assert "timestamps" in data
    assert "created_at" in data["timestamps"]


def test_guard_creates_safety_report(tmp_path):
    run_dir = os.path.join(str(tmp_path), "run")
    rc = go_evidence.main([
        "guard",
        run_dir,
        "--cmd",
        "echo hello",
    ])
    assert rc == 0
    report_path = os.path.join(run_dir, "safety-report.json")
    assert os.path.exists(report_path)
    with open(report_path, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    assert report["command"] == "echo hello"
    assert report["exit_code"] == 0
    assert "hello" in report["stdout"]
    assert report["producer"] == "go_evidence.py"


def test_guard_accepts_command_flag(tmp_path):
    run_dir = os.path.join(str(tmp_path), "run")
    rc = go_evidence.main([
        "guard",
        run_dir,
        "--command",
        "echo hello",
    ])
    assert rc == 0
    report_path = os.path.join(run_dir, "safety-report.json")
    assert os.path.exists(report_path)
    with open(report_path, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    assert report["command"] == "echo hello"
    assert report["exit_code"] == 0
    assert "hello" in report["stdout"]
    assert report["producer"] == "go_evidence.py"


def test_complete_pass_writes_final_report(tmp_path):
    evidence_dir = _setup_minimal_evidence(str(tmp_path))
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 0
    final_report = os.path.join(evidence_dir, "final-report.md")
    assert os.path.exists(final_report)
    with open(final_report, "r", encoding="utf-8") as fh:
        content = fh.read()
    assert "**Status**: pass" in content
    assert "**Reason**: ok" in content
    assert "evidence-manifest.json: present" in content
    assert "final-verdict.json: present" in content

    with open(os.path.join(evidence_dir, "evidence-manifest.json"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(os.path.join(evidence_dir, "final-verdict.json"), "r", encoding="utf-8") as fh:
        final_verdict = json.load(fh)
    _schema_validator("schemas/agent-runtime/evidence-manifest.schema.json").validate(manifest)
    _schema_validator("schemas/agent-runtime/final-verdict.schema.json").validate(final_verdict)
    assert manifest["verdict_eligibility"]["status"] == "eligible_clean"
    assert "evidence-manifest.json" in manifest["files_present"]
    assert "final-report.md" in manifest["files_present"]
    assert "final-verdict.json" in manifest["files_present"]
    assert final_verdict["final_state"] == "final_ready"
    assert final_verdict["producer_role"] == "governance"
    assert final_verdict["reviewer_summary"]["reviewer_id"] == "reviewer-1"


@pytest.mark.parametrize("verdict,expected_state", [
    ("blocked", "blocked"),
    ("fail", "failed"),
    ("escalate", "blocked"),
])
def test_non_pass_review_verdict_never_final_ready(tmp_path, verdict, expected_state):
    evidence_dir = _setup_minimal_evidence(str(tmp_path), {"verdict": verdict})
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 1
    with open(os.path.join(evidence_dir, "final-verdict.json"), "r", encoding="utf-8") as fh:
        final_verdict = json.load(fh)
    with open(os.path.join(evidence_dir, "failure-record.json"), "r", encoding="utf-8") as fh:
        failure = json.load(fh)
    assert final_verdict["final_state"] == expected_state
    assert final_verdict["final_state"] != "final_ready"
    assert failure["status"] in {"blocked", "failed"}
    with open(os.path.join(evidence_dir, "evidence-manifest.json"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert "evidence-manifest.json" in manifest["files_present"]
    assert "failure-record.json" in manifest["files_present"]
    assert "final-report.md" in manifest["files_present"]
    assert "final-verdict.json" in manifest["files_present"]


def test_finalize_subprocess_entrypoint_writes_machine_artifacts(tmp_path):
    evidence_dir = _setup_minimal_evidence(str(tmp_path))
    script = os.path.join(REPO_ROOT, "tools", "go_evidence.py")
    proc = subprocess.run(
        [sys.executable, script, "finalize", evidence_dir],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout
    for filename in ("evidence-manifest.json", "final-report.md", "final-verdict.json"):
        assert os.path.exists(os.path.join(evidence_dir, filename))


def test_tdd_finalize_blocks_without_red_green(tmp_path):
    evidence_dir = _setup_minimal_evidence(str(tmp_path))
    chain_evidence_path = os.path.join(evidence_dir, "chain-evidence.json")
    with open(chain_evidence_path, "r", encoding="utf-8") as fh:
        chain = json.load(fh)
    chain["methodology"] = {"skill_id": "tdd", "title": "tdd"}
    with open(chain_evidence_path, "w", encoding="utf-8") as fh:
        json.dump(chain, fh)
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 1


def test_tdd_finalize_passes_with_red_green(tmp_path):
    evidence_dir = _setup_minimal_evidence(str(tmp_path))
    _write(os.path.join(evidence_dir, "test-output-red.md"), "")
    _write(os.path.join(evidence_dir, "test-output-green.md"), "")
    chain_evidence_path = os.path.join(evidence_dir, "chain-evidence.json")
    with open(chain_evidence_path, "r", encoding="utf-8") as fh:
        chain = json.load(fh)
    chain["methodology"] = {"skill_id": "tdd", "title": "tdd"}
    with open(chain_evidence_path, "w", encoding="utf-8") as fh:
        json.dump(chain, fh)
    rc = go_evidence.main(["finalize", evidence_dir])
    assert rc == 0
