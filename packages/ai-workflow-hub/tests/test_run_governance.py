from __future__ import annotations

import json

from ai_workflow_hub.cli import verify_run_evidence
from ai_workflow_hub.cli import _write_chain_evidence
from ai_workflow_hub.run_governance import summarize_run_governance


def _write_state(run_dir, **fields):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(fields), encoding="utf-8")


def test_terminal_passed_status_does_not_infer_chain_trust(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(
        run_dir,
        status="passed",
        chain_status="UNKNOWN",
        final_report_status="PASS",
        final_report_consistent=True,
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["run_status"] == "passed"
    assert summary["chain_status"] == "UNKNOWN"
    assert summary["chain_trusted"] is False


def test_terminal_blocked_status_does_not_infer_chain_trust(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(run_dir, status="blocked", chain_status="UNKNOWN")

    summary = summarize_run_governance(str(run_dir))

    assert summary["run_status"] == "blocked"
    assert summary["chain_trusted"] is False


def test_explicit_chain_trust_is_preserved(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(run_dir, status="passed", chain_status="TRUSTED", chain_trusted=True)

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_status"] == "TRUSTED"
    assert summary["chain_trusted"] is True


def test_string_chain_trust_is_not_accepted(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(run_dir, status="passed", chain_status="TRUSTED", chain_trusted="true")

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_trusted"] is False


def test_nodes_style_chain_evidence_is_classified_without_inferred_trust(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(
        run_dir,
        status="passed",
        chain_status="UNKNOWN",
        final_report_status="PASS",
        final_report_consistent=True,
    )
    (run_dir / "chain-evidence.json").write_text(
        json.dumps({
            "run_id": "run-nodes",
            "status": "passed",
            "backend": "opencode",
            "nodes": {
                "planner": {"backend": "opencode", "exit_code": 0},
                "executor": {"backend": "opencode", "exit_code": 0},
            },
        }),
        encoding="utf-8",
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "ai_workflow_hub_nodes"
    assert "not canonical acceptance evidence" in summary["chain_evidence_diagnostic"]
    assert summary["governance"]["chain_evidence_shape"] == "ai_workflow_hub_nodes"
    assert summary["chain_trusted"] is False
    assert summary["chain_status"] == "UNTRUSTED_NODES_STYLE"


def test_write_chain_evidence_shape_is_visible_and_untrusted(tmp_path):
    run_dir = tmp_path / "runs" / "demo-project" / "run-shape"
    state = {
        "run_id": "run-shape",
        "status": "passed",
        "chain_status": "UNKNOWN",
        "final_report_status": "PASS",
        "final_report_consistent": True,
    }

    _write_chain_evidence(str(run_dir), state)
    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "ai_workflow_hub_nodes"
    assert summary["chain_trusted"] is False
    assert summary["chain_status"] == "UNTRUSTED_NODES_STYLE"


def test_nodes_style_chain_evidence_overrides_stale_trusted_state(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(
        run_dir,
        status="passed",
        chain_status="TRUSTED",
        chain_trusted=True,
        final_report_status="PASS",
        final_report_consistent=True,
    )
    (run_dir / "chain-evidence.json").write_text(
        json.dumps({
            "run_id": "run-stale-trusted",
            "status": "passed",
            "nodes": {"executor": {"backend": "opencode", "exit_code": 0}},
        }),
        encoding="utf-8",
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "ai_workflow_hub_nodes"
    assert summary["chain_status"] == "UNTRUSTED_NODES_STYLE"
    assert summary["chain_trusted"] is False


def test_verify_run_evidence_reports_untrusted_passed_run(tmp_path):
    run_dir = tmp_path / "runs" / "demo-project" / "run-001"
    _write_state(
        run_dir,
        status="passed",
        chain_status="UNKNOWN",
        final_report_status="PASS",
        final_report_consistent=True,
    )

    result = verify_run_evidence("run-001", "demo-project", hub_dir_override=tmp_path)

    assert result["status"] == "passed"
    assert result["chain_trusted"] is False
    assert "chain UNKNOWN (status=passed)" in result["reasons"]


def test_write_chain_evidence_remains_untrusted_for_verify_path(tmp_path):
    run_dir = tmp_path / "runs" / "demo-project" / "run-002"
    state = {
        "run_id": "run-002",
        "status": "passed",
        "chain_status": "UNKNOWN",
        "final_report_status": "PASS",
        "final_report_consistent": True,
    }

    _write_chain_evidence(str(run_dir), state)
    result = verify_run_evidence("run-002", "demo-project", hub_dir_override=tmp_path)

    assert (run_dir / "chain-evidence.json").exists()
    assert result["chain_status"] == "UNTRUSTED_NODES_STYLE"
    assert result["chain_trusted"] is False
    assert "chain UNTRUSTED_NODES_STYLE (status=passed)" in result["reasons"]
    state_after = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state_after["chain_trusted"] is False
    assert state_after["chain_status"] == "UNTRUSTED_NODES_STYLE"
    serialized = json.dumps({
        "state": state_after,
        "chain": json.loads((run_dir / "chain-evidence.json").read_text(encoding="utf-8")),
        "verify": result,
    })
    assert "final_ready" not in serialized
    assert "final-ready" not in serialized
    assert "final ready" not in serialized


def test_state_argument_takes_precedence_over_stale_state_file(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(run_dir, status="failed", chain_status="UNKNOWN", final_report_consistent=False)

    summary = summarize_run_governance(
        str(run_dir),
        state={
            "status": "passed",
            "chain_status": "TRUSTED",
            "chain_trusted": True,
            "final_report_status": "PASS",
            "final_report_consistent": True,
        },
    )

    assert summary["run_status"] == "passed"
    assert summary["chain_status"] == "TRUSTED"
    assert summary["chain_trusted"] is True
    assert summary["final_report_consistent"] is True
