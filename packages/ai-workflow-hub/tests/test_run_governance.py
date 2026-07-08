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
    assert summary["chain_status"] == "MISSING_CHAIN_EVIDENCE"
    assert summary["chain_trusted"] is False


def test_terminal_blocked_status_does_not_infer_chain_trust(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(run_dir, status="blocked", chain_status="UNKNOWN")

    summary = summarize_run_governance(str(run_dir))

    assert summary["run_status"] == "blocked"
    assert summary["chain_status"] == "MISSING_CHAIN_EVIDENCE"
    assert summary["chain_trusted"] is False


def test_explicit_chain_trust_is_preserved_with_canonical_evidence(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(run_dir, status="passed", chain_status="TRUSTED", chain_trusted=True)
    (run_dir / "chain-evidence.json").write_text(
        json.dumps({
            "evidence_files": ["test-output.md"],
            "timestamps": {"created_at": "2026-07-08T12:00:00Z"},
        }),
        encoding="utf-8",
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_status"] == "TRUSTED"
    assert summary["chain_trusted"] is True


def test_missing_chain_evidence_overrides_stale_trusted_state(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(
        run_dir,
        status="passed",
        chain_status="TRUSTED",
        chain_trusted=True,
        final_report_status="PASS",
        final_report_consistent=True,
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "missing"
    assert summary["chain_status"] == "MISSING_CHAIN_EVIDENCE"
    assert summary["chain_trusted"] is False
    assert summary["chain_evidence_adapter"]["normalization_status"] == "blocked"


def test_string_chain_trust_is_not_accepted(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(run_dir, status="passed", chain_status="TRUSTED", chain_trusted="true")

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_trusted"] is False


def test_nodes_style_chain_evidence_is_classified_without_inferred_trust(tmp_path):
    run_dir = tmp_path / "run"
    stdout_log = run_dir / "planner.stdout"
    stderr_log = run_dir / "planner.stderr"
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_log.write_text("planner output", encoding="utf-8")
    stderr_log.write_text("planner warning", encoding="utf-8")
    _write_state(
        run_dir,
        status="passed",
        chain_status="UNKNOWN",
        final_report_status="PASS",
        final_report_consistent=True,
        created_at="2026-07-08T12:00:00Z",
        mode="apply",
        planner="agentic-governance",
        task="task-hub",
        run_id="run-state",
        executor_id="executor-hub",
    )
    (run_dir / "chain-evidence.json").write_text(
        json.dumps({
            "run_id": "run-nodes",
            "status": "passed",
            "backend": "opencode",
            "nodes": {
                "planner": {
                    "backend": "opencode",
                    "exit_code": 0,
                    "stdout_log": str(stdout_log),
                    "stderr_log": str(stderr_log),
                },
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
    adapter = summary["chain_evidence_adapter"]
    assert adapter["normalized"] is True
    assert adapter["normalization_status"] == "normalized"
    assert adapter["acceptance_candidate"] is False
    normalized = adapter["normalized_chain_evidence"]
    assert normalized["run_id"] == "run-nodes"
    assert normalized["executor_id"] == "executor-hub"
    assert normalized["timestamps"]["created_at"] == "2026-07-08T12:00:00Z"
    assert str(run_dir / "chain-evidence.json") in normalized["evidence_files"]
    assert str(stdout_log) in normalized["evidence_files"]
    assert normalized["methodology"]["worker_results"][0]["status"] == "passed"


def test_nodes_style_chain_evidence_takes_adapter_precedence_over_go_shape(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    _write_state(run_dir, status="passed", chain_status="UNKNOWN")
    (run_dir / "chain-evidence.json").write_text(
        json.dumps({
            "run_id": "run-mixed",
            "nodes": {"executor": {"backend": "opencode", "exit_code": 0}},
            "evidence_files": ["chain-evidence.json"],
            "timestamps": {"created_at": "2026-07-08T12:00:00Z"},
        }),
        encoding="utf-8",
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "ai_workflow_hub_nodes"
    assert summary["chain_evidence_adapter"]["source_shape"] == "ai_workflow_hub_nodes"
    assert summary["chain_evidence_adapter"]["normalization_status"] == "normalized"
    assert summary["chain_trusted"] is False


def test_go_evidence_chain_adapter_blocks_invalid_passthrough_shape(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    _write_state(run_dir, status="passed", chain_status="UNKNOWN")
    (run_dir / "chain-evidence.json").write_text(
        json.dumps({
            "run_id": "run-invalid-go-shape",
            "evidence_files": "chain-evidence.json",
            "timestamps": "bad",
        }),
        encoding="utf-8",
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "go_evidence_v1"
    adapter = summary["chain_evidence_adapter"]
    assert adapter["source_shape"] == "go_evidence_v1"
    assert adapter["normalization_status"] == "blocked"
    assert adapter["normalized"] is False
    assert adapter["acceptance_candidate"] is False


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
    assert summary["chain_evidence_adapter"]["normalized"] is True
    assert summary["chain_evidence_adapter"]["acceptance_candidate"] is False


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


def test_invalid_chain_evidence_overrides_stale_trusted_state(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(
        run_dir,
        status="passed",
        chain_status="TRUSTED",
        chain_trusted=True,
        final_report_status="PASS",
        final_report_consistent=True,
    )
    (run_dir / "chain-evidence.json").write_text("{not json", encoding="utf-8")

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "invalid"
    assert summary["chain_status"] == "INVALID_CHAIN_EVIDENCE"
    assert summary["chain_trusted"] is False
    assert summary["chain_evidence_adapter"]["normalization_status"] == "blocked"


def test_non_object_chain_evidence_overrides_stale_trusted_state(tmp_path):
    run_dir = tmp_path / "run"
    _write_state(
        run_dir,
        status="passed",
        chain_status="TRUSTED",
        chain_trusted=True,
        final_report_status="PASS",
        final_report_consistent=True,
    )
    (run_dir / "chain-evidence.json").write_text("[]", encoding="utf-8")

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "invalid"
    assert summary["chain_status"] == "INVALID_CHAIN_EVIDENCE"
    assert summary["chain_trusted"] is False


def test_unknown_chain_evidence_overrides_stale_trusted_state(tmp_path):
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
        json.dumps({"run_id": "run-unknown", "status": "passed"}),
        encoding="utf-8",
    )

    summary = summarize_run_governance(str(run_dir))

    assert summary["chain_evidence_shape"] == "unknown"
    assert summary["chain_status"] == "UNKNOWN_CHAIN_EVIDENCE"
    assert summary["chain_trusted"] is False
    assert summary["chain_evidence_adapter"]["normalization_status"] == "blocked"


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
    assert "chain MISSING_CHAIN_EVIDENCE (status=passed)" in result["reasons"]


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
    (run_dir / "chain-evidence.json").write_text(
        json.dumps({
            "evidence_files": ["test-output.md"],
            "timestamps": {"created_at": "2026-07-08T12:00:00Z"},
        }),
        encoding="utf-8",
    )

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
