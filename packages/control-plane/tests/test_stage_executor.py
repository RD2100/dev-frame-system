import json
import subprocess
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for

from control_plane import stage_executor
from control_plane.run_index import build_run_index


REPO_ROOT = Path(__file__).resolve().parents[3]


class _CompletedProcess:
    returncode = 0
    stdout = "ok\n"
    stderr = ""


def test_execute_closure_writes_limited_paper_final_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-test")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _CompletedProcess())
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\ncurrent_stage: closure\n", encoding="utf-8")
    (paper_root / "PAPER_STATE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "acceptance_status: accepted_with_limitation",
            "final_acceptance: true",
            "human_required: false",
            "human_gate_triggered: false",
        ]) + "\n",
        encoding="utf-8",
    )
    (paper_root / "paper_task").mkdir()
    privacy_path = paper_root / "paper_task" / "PRIVACY_ATTESTATION.yaml"
    privacy_path.write_text("contains_real_paper_full_text: false\n", encoding="utf-8")
    (paper_root / "review").mkdir()
    (paper_root / "review" / "REVIEW_REPORT.md").write_text("# Review\n", encoding="utf-8")
    (paper_root / "evidence").mkdir()
    with zipfile.ZipFile(paper_root / "evidence" / "ref-paper-review-pack.zip", "w") as zf:
        zf.writestr("review/REVIEW_REPORT.md", "# Review\n")

    result = stage_executor.execute_closure(paper_root)

    final_verdict_path = paper_root / "closure" / "FINAL_VERDICT.json"
    assert result.status == "completed"
    assert str(final_verdict_path) in result.outputs
    payload = json.loads(final_verdict_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(encoding="utf-8-sig")
    )
    Draft202012Validator(schema).validate(payload)
    assert payload["final_state"] == "accepted_with_limitation"
    assert payload["reviewer_summary"]["verdict"] == "pass"
    assert any(gate["result"] == "warning" for gate in payload["gate_summary"])
    assert any("dry-run only" in item for item in payload["limitations"])
    flow = json.loads((paper_root / "closure" / "FLOW_OUTCOME.json").read_text(encoding="utf-8"))
    assert flow["final_verdict_state"] == "accepted_with_limitation"
    assert flow["final_verdict_path"] == str(final_verdict_path)

    index = build_run_index(tmp_path / "runtime", paper_project_dirs=[paper_root])
    record = [item["record"] for item in index["runs"] if item["adapter_id"] == "paper"][0]
    _run_record_validator().validate(record)
    assert record["acceptance_state"] == "accepted_with_limitation"
    assert record["gate_state"] == "gate_limited"
    assert record["final_verdict_ref"]["verdict_id"] == "fv-paper-ref-paper-test"


def _run_record_validator():
    schema = json.loads(
        (REPO_ROOT / "schemas/runtime-governance/run-record.schema.json").read_text(encoding="utf-8-sig")
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)
