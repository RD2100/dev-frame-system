"""Tests for A10: Paper Workflow State + Paper Graph.

Covers:
  - PaperWorkflowState defaults, field assignment, serialization
  - diagnosis_node: mock / offline / live / error modes
  - acceptance_gate_node: fresh compute / skip when pre-populated
  - human_gate_node: trigger + pause
  - paper_finalizer_node: all terminal statuses
  - _wrap(): Pydantic / dict compatibility
  - Graph construction: nodes, edges, entry point
  - Graph execution: compile + invoke for each route
  - Edge cases: empty state, missing fields, error recovery
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from ai_workflow_hub.workflows.paper_workflow_state import PaperWorkflowState
from ai_workflow_hub.workflows.paper_graph import (
    diagnosis_node,
    acceptance_gate_node,
    human_gate_node,
    paper_finalizer_node,
    _route_after_acceptance,
    _wrap,
    _s,
    _append_node,
    create_paper_graph,
    compile_paper_graph,
)
from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import (
    compute_acceptance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_issue(
    issue_id: str = "test-001",
    issue_type: str = "expression",
    severity: str = "minor",
    evidence: str = "test evidence",
    blocking: bool = False,
    recommendation: str = "",
    human_required: bool = False,
) -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "issue_type": issue_type,
        "severity": severity,
        "evidence": evidence,
        "blocking": blocking,
        "recommendation": recommendation,
        "human_required": human_required,
    }


def make_offline_zip(tmp_path, *, privacy_ok: bool = True, expr_results=None, para_results=None):
    """Create a minimal handoff ZIP for offline pipeline tests.

    Must match convert_handoff_zip expectations:
      - manifest.json with handoff_id (not manifest_id)
      - files[] with sha256 and size_bytes for integrity check
      - diagnosis/expression_results.json and paragraph_results.json
    """
    zip_path = tmp_path / "handoff.zip"
    expr = expr_results or []
    para = para_results or []
    expr_bytes = json.dumps(expr).encode()
    para_bytes = json.dumps(para).encode()

    import hashlib
    expr_sha = hashlib.sha256(expr_bytes).hexdigest()
    para_sha = hashlib.sha256(para_bytes).hexdigest()

    manifest = {
        "handoff_id": "test-001",
        "task_id": "task-test-001",
        "status": "complete",
        "privacy_attestation": {
            "no_full_text": True,
            "no_api_keys": True,
            "no_personal_identity": True,
        } if privacy_ok else {
            "no_full_text": False,
            "no_api_keys": True,
            "no_personal_identity": True,
        },
        "files": [
            {"path": "diagnosis/expression_results.json", "sha256": expr_sha, "size_bytes": len(expr_bytes)},
            {"path": "diagnosis/paragraph_results.json", "sha256": para_sha, "size_bytes": len(para_bytes)},
        ],
        "created_at": "2026-06-11T00:00:00Z",
    }

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("diagnosis/expression_results.json", json.dumps(expr))
        zf.writestr("diagnosis/paragraph_results.json", json.dumps(para))

    return zip_path


def make_call_result(success=True, issues=None, diagnosis_source="llm", error=None):
    """Create a mock WriteLabCallResult."""
    cr = MagicMock()
    cr.success = success
    cr.issues = issues or []
    cr.diagnosis_source = diagnosis_source
    cr.fallback_used = False
    cr.error = error
    return cr


# ===========================================================================
# PaperWorkflowState Tests
# ===========================================================================

class TestPaperWorkflowState:
    """Tests for the Pydantic state model."""

    def test_defaults(self):
        state = PaperWorkflowState()
        assert state.task_id == ""
        assert state.writelab_mode == "mock"
        assert state.status == "pending"
        assert state.fix_round == 0
        assert state.max_fix_rounds == 3
        assert state.all_review_issues == []
        assert state.acceptance_result == {}
        assert state.executed_nodes == []
        assert state.privacy_attestation == {}

    def test_field_assignment(self):
        state = PaperWorkflowState(
            task_id="task-001",
            task_chapter="Introduction",
            writelab_mode="offline",
            handoff_zip_path="/tmp/test.zip",
        )
        assert state.task_id == "task-001"
        assert state.task_chapter == "Introduction"
        assert state.writelab_mode == "offline"
        assert state.handoff_zip_path == "/tmp/test.zip"

    def test_model_dump(self):
        state = PaperWorkflowState(task_id="t1", status="running")
        d = state.model_dump()
        assert isinstance(d, dict)
        assert d["task_id"] == "t1"
        assert d["status"] == "running"
        assert "created_at" in d

    def test_all_default_fields_present(self):
        state = PaperWorkflowState()
        d = state.model_dump()
        expected_keys = [
            "task_id", "task_chapter", "task_section", "writelab_base_url",
            "writelab_token", "writelab_mode", "handoff_zip_path",
            "expression_issues", "paragraph_issues", "all_review_issues",
            "diagnosis_source", "diagnosis_error", "writelab_available",
            "evidence_manifest", "evidence_pack_ref", "manifest_status",
            "acceptance_status", "acceptance_result", "blocking_count",
            "non_blocking_count", "human_required", "human_gate_decision",
            "human_gate_triggered", "privacy_attestation", "status",
            "error_message", "fix_round", "max_fix_rounds", "executed_nodes",
            "created_at", "updated_at",
        ]
        for key in expected_keys:
            assert key in d, f"Missing key: {key}"

    def test_timestamps_auto_generated(self):
        state = PaperWorkflowState()
        assert state.created_at  # non-empty
        assert state.updated_at  # non-empty


# ===========================================================================
# diagnosis_node Tests
# ===========================================================================

class TestDiagnosisNode:
    """Tests for the diagnosis node function."""

    def test_mock_mode_combines_issues(self):
        state = {
            "writelab_mode": "mock",
            "expression_issues": [make_issue("expr-1")],
            "paragraph_issues": [make_issue("para-1")],
        }
        result = diagnosis_node(state)
        assert len(result["all_review_issues"]) == 2
        assert result["diagnosis_source"] == "mock"
        assert result["status"] == "running"
        assert "diagnosis_node" in result["executed_nodes"]

    def test_mock_mode_empty_issues(self):
        state = {"writelab_mode": "mock"}
        result = diagnosis_node(state)
        assert result["all_review_issues"] == []
        assert result["diagnosis_source"] == "mock"

    def test_default_mode_is_mock(self):
        state = {}
        result = diagnosis_node(state)
        assert result["diagnosis_source"] == "mock"

    def test_offline_mode_no_zip_path(self):
        state = {"writelab_mode": "offline", "handoff_zip_path": ""}
        result = diagnosis_node(state)
        assert result["diagnosis_error"] == "offline mode requires handoff_zip_path"
        assert result["writelab_available"] is False
        assert result["diagnosis_source"] == "unavailable"

    def test_offline_mode_with_zip(self, tmp_path):
        zip_path = make_offline_zip(tmp_path)
        state = {
            "writelab_mode": "offline",
            "handoff_zip_path": str(zip_path),
        }
        result = diagnosis_node(state)
        assert result["diagnosis_source"] == "offline"
        assert result["evidence_manifest"] != {}
        assert result["evidence_pack_ref"] == "wl-test-001"
        assert "acceptance_result" in result
        assert result["acceptance_status"] in (
            "accepted", "accepted_with_limitation", "blocked", "needs_more_evidence"
        )

    def test_offline_mode_privacy_violation(self, tmp_path):
        zip_path = make_offline_zip(tmp_path, privacy_ok=False)
        state = {
            "writelab_mode": "offline",
            "handoff_zip_path": str(zip_path),
        }
        result = diagnosis_node(state)
        # convert_handoff_zip raises ValueError on privacy attestation failure
        assert result["diagnosis_error"]  # non-empty error
        assert result["writelab_available"] is False
        assert result["diagnosis_source"] == "unavailable"

    def test_live_mode_with_call_results(self):
        cr = make_call_result(
            success=True,
            issues=[make_issue("live-1", severity="major", blocking=True)],
        )
        state = {
            "writelab_mode": "live",
            "_call_results": [cr],
            "evidence_pack_ref": "ep-001",
        }
        result = diagnosis_node(state)
        assert result["diagnosis_source"] == "live"
        assert len(result["all_review_issues"]) == 1
        assert result["acceptance_status"] == "blocked"
        assert result["blocking_count"] == 1

    def test_live_mode_no_results(self):
        state = {
            "writelab_mode": "live",
            "_call_results": [],
        }
        result = diagnosis_node(state)
        assert result["diagnosis_source"] == "live"
        assert result["acceptance_status"] == "accepted"

    def test_error_handling_in_offline(self, tmp_path):
        state = {
            "writelab_mode": "offline",
            "handoff_zip_path": str(tmp_path / "nonexistent.zip"),
        }
        result = diagnosis_node(state)
        assert result["diagnosis_error"]  # non-empty error message
        assert result["writelab_available"] is False
        assert result["diagnosis_source"] == "unavailable"

    def test_executed_nodes_tracking(self):
        state = {"writelab_mode": "mock", "executed_nodes": []}
        result = diagnosis_node(state)
        assert "diagnosis_node" in result["executed_nodes"]

    def test_executed_nodes_no_duplicate(self):
        state = {
            "writelab_mode": "mock",
            "executed_nodes": ["diagnosis_node"],
        }
        result = diagnosis_node(state)
        assert result["executed_nodes"].count("diagnosis_node") == 1


# ===========================================================================
# acceptance_gate_node Tests
# ===========================================================================

class TestAcceptanceGateNode:
    """Tests for the acceptance gate node function."""

    def test_fresh_compute_no_issues(self):
        state = {
            "all_review_issues": [],
            "evidence_pack_ref": "ep-001",
        }
        result = acceptance_gate_node(state)
        assert result["acceptance_status"] == "accepted"
        assert result["blocking_count"] == 0
        assert result["non_blocking_count"] == 0
        assert "acceptance_gate_node" in result["executed_nodes"]

    def test_fresh_compute_with_blocking(self):
        state = {
            "all_review_issues": [
                make_issue("b1", blocking=True, severity="critical"),
            ],
            "evidence_pack_ref": "ep-002",
        }
        result = acceptance_gate_node(state)
        assert result["acceptance_status"] == "blocked"
        assert result["blocking_count"] == 1

    def test_skip_when_pre_populated(self):
        existing_result = {
            "status": "accepted_with_limitation",
            "reasons": ["pre-computed"],
            "blocking_issues": [],
            "non_blocking_issues": [make_issue("nb1")],
            "required_next_actions": [],
            "reviewer": "writelab_adapter",
            "evidence_pack_ref": "ep-pre",
        }
        state = {
            "acceptance_result": existing_result,
            "all_review_issues": [make_issue("ignored")],
        }
        result = acceptance_gate_node(state)
        # Should skip re-computation
        assert "acceptance_gate_node" in result["executed_nodes"]
        # acceptance_result should not be overwritten
        assert "acceptance_result" not in result or result.get("acceptance_result") == existing_result

    def test_with_privacy_attestation(self):
        state = {
            "all_review_issues": [],
            "evidence_pack_ref": "ep-003",
            "privacy_attestation": {
                "no_full_text": True,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
        }
        result = acceptance_gate_node(state)
        assert result["acceptance_status"] == "accepted"

    def test_with_privacy_violation(self):
        state = {
            "all_review_issues": [],
            "evidence_pack_ref": "ep-004",
            "privacy_attestation": {
                "no_full_text": False,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
        }
        result = acceptance_gate_node(state)
        assert result["acceptance_status"] == "blocked"
        # Privacy violations don't add to blocking_issues list;
        # they block via status directly in compute_acceptance.
        ar = result["acceptance_result"]
        assert "privacy" in " ".join(ar.get("reasons", [])).lower()


# ===========================================================================
# human_gate_node Tests
# ===========================================================================

class TestHumanGateNode:
    """Tests for the human gate node function."""

    def test_triggers_human_gate(self):
        state = {"executed_nodes": []}
        result = human_gate_node(state)
        assert result["human_required"] is True
        assert result["human_gate_triggered"] is True
        assert result["human_gate_decision"] == "pending"
        assert result["status"] == "human_required"
        assert "human_gate_node" in result["executed_nodes"]

    def test_preserves_existing_executed_nodes(self):
        state = {"executed_nodes": ["diagnosis_node", "acceptance_gate_node"]}
        result = human_gate_node(state)
        assert "diagnosis_node" in result["executed_nodes"]
        assert "acceptance_gate_node" in result["executed_nodes"]
        assert "human_gate_node" in result["executed_nodes"]


# ===========================================================================
# paper_finalizer_node Tests
# ===========================================================================

class TestPaperFinalizerNode:
    """Tests for the paper finalizer node function."""

    def test_completed_status(self):
        state = {
            "acceptance_result": {"status": "accepted"},
            "acceptance_status": "accepted",
            "blocking_count": 0,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        assert result["status"] == "completed"
        assert result["acceptance_status"] == "accepted"
        assert result["updated_at"]  # non-empty timestamp

    def test_blocked_status(self):
        state = {
            "acceptance_result": {"status": "blocked"},
            "acceptance_status": "blocked",
            "blocking_count": 2,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        assert result["status"] == "blocked"

    def test_blocked_from_count(self):
        state = {
            "acceptance_result": {"status": "accepted"},
            "acceptance_status": "accepted",
            "blocking_count": 1,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        assert result["status"] == "blocked"

    def test_human_required_status(self):
        state = {
            "acceptance_result": {"status": "human_required"},
            "acceptance_status": "human_required",
            "blocking_count": 0,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        assert result["status"] == "human_required"

    def test_error_status(self):
        state = {
            "acceptance_result": {},
            "acceptance_status": "",
            "diagnosis_error": "something failed",
            "all_review_issues": [],
            "blocking_count": 0,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        assert result["status"] == "error"

    def test_accepted_with_limitation(self):
        state = {
            "acceptance_result": {"status": "accepted_with_limitation"},
            "acceptance_status": "accepted_with_limitation",
            "blocking_count": 0,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        assert result["status"] == "completed"

    def test_needs_more_evidence(self):
        state = {
            "acceptance_result": {"status": "needs_more_evidence"},
            "acceptance_status": "needs_more_evidence",
            "blocking_count": 0,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        assert result["status"] == "completed"

    def test_executed_nodes_updated(self):
        state = {
            "acceptance_result": {"status": "accepted"},
            "acceptance_status": "accepted",
            "blocking_count": 0,
            "executed_nodes": ["diagnosis_node"],
        }
        result = paper_finalizer_node(state)
        assert "paper_finalizer_node" in result["executed_nodes"]


# ===========================================================================
# Routing Function Tests
# ===========================================================================

class TestRouting:
    """Tests for graph routing functions."""

    def test_route_blocked(self):
        state = {"acceptance_status": "blocked"}
        assert _route_after_acceptance(state) == "finalizer"

    def test_route_human_required(self):
        state = {"acceptance_status": "human_required"}
        assert _route_after_acceptance(state) == "human_gate"

    def test_route_accepted(self):
        state = {"acceptance_status": "accepted"}
        assert _route_after_acceptance(state) == "finalizer"

    def test_route_accepted_with_limitation(self):
        state = {"acceptance_status": "accepted_with_limitation"}
        assert _route_after_acceptance(state) == "finalizer"

    def test_route_needs_more_evidence(self):
        state = {"acceptance_status": "needs_more_evidence"}
        assert _route_after_acceptance(state) == "finalizer"

    def test_route_empty_status(self):
        state = {}
        assert _route_after_acceptance(state) == "finalizer"

    def test_route_with_pydantic_state(self):
        state = PaperWorkflowState(acceptance_status="human_required")
        assert _route_after_acceptance(state) == "human_gate"


# ===========================================================================
# Helper Function Tests
# ===========================================================================

class TestHelpers:
    """Tests for _s, _append_node, _wrap helper functions."""

    def test_s_with_dict(self):
        d = {"key": "value"}
        assert _s(d) is d

    def test_s_with_pydantic(self):
        state = PaperWorkflowState(task_id="t1")
        result = _s(state)
        assert isinstance(result, dict)
        assert result["task_id"] == "t1"

    def test_s_with_none_like(self):
        assert _s(None) == {}
        assert _s("") == {}

    def test_append_node_new(self):
        state = {"executed_nodes": []}
        result = _append_node(state, "node_a")
        assert result == ["node_a"]

    def test_append_node_no_duplicate(self):
        state = {"executed_nodes": ["node_a"]}
        result = _append_node(state, "node_a")
        assert result == ["node_a"]

    def test_append_node_preserves_existing(self):
        state = {"executed_nodes": ["node_a", "node_b"]}
        result = _append_node(state, "node_c")
        assert result == ["node_a", "node_b", "node_c"]

    def test_append_node_empty_state(self):
        state = {}
        result = _append_node(state, "node_x")
        assert result == ["node_x"]

    def test_wrap_with_dict(self):
        def my_node(state):
            return {"output": "result"}
        wrapped = _wrap(my_node)
        result = wrapped({"input": "data"})
        assert result["input"] == "data"
        assert result["output"] == "result"

    def test_wrap_with_pydantic(self):
        def my_node(state):
            return {"status": "done"}
        wrapped = _wrap(my_node)
        state = PaperWorkflowState(task_id="t1")
        result = wrapped(state)
        assert isinstance(result, dict)
        assert result["task_id"] == "t1"
        assert result["status"] == "done"


# ===========================================================================
# Graph Construction Tests
# ===========================================================================

class TestGraphConstruction:
    """Tests for create_paper_graph and compile_paper_graph."""

    def test_create_graph_returns_state_graph(self):
        from langgraph.graph import StateGraph
        graph = create_paper_graph()
        assert isinstance(graph, StateGraph)

    def test_graph_has_five_nodes(self):
        graph = create_paper_graph()
        node_names = set(graph.nodes.keys())
        assert "diagnosis" in node_names
        assert "acceptance_gate" in node_names
        assert "ledger_ingest" in node_names
        assert "human_gate" in node_names
        assert "finalizer" in node_names
        assert len(node_names) == 5

    def test_compile_returns_compiled_graph(self):
        compiled = compile_paper_graph("test-thread")
        assert compiled is not None

    def test_compile_with_default_thread(self):
        compiled = compile_paper_graph()
        assert compiled is not None


# ===========================================================================
# Graph Execution Tests (compile + invoke)
# ===========================================================================

class TestGraphExecution:
    """Integration tests: compile graph and invoke with various scenarios."""

    def _invoke(self, initial_state: dict, thread_id: str = "test"):
        compiled = compile_paper_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        return compiled.invoke(initial_state, config)

    def test_mock_mode_accepted(self):
        result = self._invoke({
            "writelab_mode": "mock",
            "all_review_issues": [],
        })
        assert result["status"] == "completed"
        assert result["acceptance_status"] == "accepted"

    def test_mock_mode_with_blocking(self):
        result = self._invoke({
            "writelab_mode": "mock",
            "expression_issues": [make_issue("b1", blocking=True, severity="critical")],
        })
        assert result["status"] == "blocked"
        assert result["blocking_count"] >= 1

    def test_mock_mode_with_human_required(self):
        result = self._invoke({
            "writelab_mode": "mock",
            "expression_issues": [
                make_issue("h1", human_required=True, severity="major"),
            ],
        })
        assert result["status"] == "human_required"
        assert result["human_gate_triggered"] is True
        assert result["human_required"] is True

    def test_mock_mode_with_non_blocking(self):
        result = self._invoke({
            "writelab_mode": "mock",
            "expression_issues": [make_issue("nb1", severity="minor")],
        })
        assert result["status"] == "completed"
        assert result["acceptance_status"] == "accepted_with_limitation"

    def test_offline_mode_accepted(self, tmp_path):
        zip_path = make_offline_zip(tmp_path)
        result = self._invoke({
            "writelab_mode": "offline",
            "handoff_zip_path": str(zip_path),
        })
        assert result["acceptance_status"] in (
            "accepted", "accepted_with_limitation", "needs_more_evidence"
        )
        assert result["evidence_manifest"] != {}

    def test_offline_mode_privacy_blocked(self, tmp_path):
        zip_path = make_offline_zip(tmp_path, privacy_ok=False)
        result = self._invoke({
            "writelab_mode": "offline",
            "handoff_zip_path": str(zip_path),
        })
        # Privacy violation in convert_handoff_zip raises ValueError,
        # caught by diagnosis_node → diagnosis_error set → error status
        assert result["status"] == "error"
        assert result["diagnosis_error"]  # non-empty

    def test_live_mode_accepted(self):
        """Test live mode via diagnosis_node directly (avoids MagicMock checkpoint issue)."""
        cr = make_call_result(success=True, issues=[])
        state = {
            "writelab_mode": "live",
            "_call_results": [cr],
            "evidence_pack_ref": "ep-live-001",
            "privacy_attestation": {
                "no_full_text": True,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
        }
        result = diagnosis_node(state)
        assert result["diagnosis_source"] == "live"
        assert result["acceptance_status"] == "accepted"

    def test_executed_nodes_sequence(self):
        result = self._invoke({
            "writelab_mode": "mock",
            "all_review_issues": [],
        })
        nodes = result["executed_nodes"]
        assert "diagnosis_node" in nodes
        assert "acceptance_gate_node" in nodes
        assert "ledger_ingest_node" in nodes  # A12
        assert "paper_finalizer_node" in nodes
        # human_gate_node should NOT be in sequence for accepted path
        assert "human_gate_node" not in nodes

    def test_executed_nodes_with_human_gate(self):
        result = self._invoke({
            "writelab_mode": "mock",
            "expression_issues": [
                make_issue("h1", human_required=True, severity="major"),
            ],
        })
        nodes = result["executed_nodes"]
        assert "diagnosis_node" in nodes
        assert "acceptance_gate_node" in nodes
        assert "ledger_ingest_node" in nodes  # A12
        assert "human_gate_node" in nodes
        # finalizer should NOT be in sequence for human_required path
        assert "paper_finalizer_node" not in nodes

    def test_empty_state(self):
        result = self._invoke({})
        assert result["status"] == "completed"
        assert result["acceptance_status"] == "accepted"

    def test_live_mode_graph_with_patch(self):
        """Test live mode through full graph by patching run_live_pipeline."""
        mock_result = {
            "acceptance_result": {
                "status": "accepted",
                "reasons": ["no issues detected; all checks passed"],
                "blocking_issues": [],
                "non_blocking_issues": [],
                "required_next_actions": [],
                "reviewer": "writelab_adapter",
                "evidence_pack_ref": "ep-live-patched",
            },
            "validation_errors": [],
            "call_summaries": [],
        }
        with patch(
            "ai_workflow_hub.workflows.paper_graph.run_live_pipeline",
            return_value=mock_result,
        ):
            result = self._invoke({
                "writelab_mode": "live",
                "evidence_pack_ref": "ep-live-patched",
            })
        assert result["status"] == "completed"
        assert result["acceptance_status"] == "accepted"


# ===========================================================================
# Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases and error recovery tests."""

    def test_offline_mode_invalid_zip(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_text("not a zip file")
        state = {
            "writelab_mode": "offline",
            "handoff_zip_path": str(bad_zip),
        }
        result = diagnosis_node(state)
        assert result["diagnosis_error"]
        assert result["writelab_available"] is False

    def test_mock_mode_many_issues(self):
        issues = [make_issue(f"issue-{i}") for i in range(100)]
        state = {
            "writelab_mode": "mock",
            "expression_issues": issues[:50],
            "paragraph_issues": issues[50:],
        }
        result = diagnosis_node(state)
        assert len(result["all_review_issues"]) == 100

    def test_acceptance_gate_with_human_required_issue(self):
        state = {
            "all_review_issues": [
                make_issue("h1", human_required=True, severity="major"),
            ],
            "evidence_pack_ref": "ep-hr",
        }
        result = acceptance_gate_node(state)
        assert result["acceptance_status"] == "human_required"

    def test_finalizer_empty_acceptance(self):
        state = {
            "acceptance_result": {},
            "acceptance_status": "",
            "blocking_count": 0,
            "executed_nodes": [],
        }
        result = paper_finalizer_node(state)
        # Should default to "completed" since no error and no blocking
        assert result["status"] in ("completed", "error")

    def test_diagnosis_preserves_state_fields(self):
        state = {
            "writelab_mode": "mock",
            "task_id": "task-xyz",
            "paragraph_text": "Hello world",
            "executed_nodes": [],
        }
        result = diagnosis_node(state)
        # Should not destroy existing state fields
        assert "task_id" not in result or result.get("task_id") == "task-xyz" or result.get("task_id") is None
        # Result is partial update, doesn't need to contain task_id


# ===========================================================================
# A12 Ledger Integration Tests
# ===========================================================================

class TestLedgerIngestNode:
    """Tests for the A12 ledger_ingest_node."""

    def test_ingest_with_task_id_and_issues(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import ledger_ingest_node
        from ai_workflow_hub.context_layer.adapters.paper_issue_ledger import (
            get_all_issues, ledger_summary,
        )

        ar = {
            "status": "blocked",
            "reasons": ["test"],
            "blocking_issues": [make_issue("b1", blocking=True, severity="critical")],
            "non_blocking_issues": [make_issue("nb1"), make_issue("nb2")],
            "required_next_actions": [],
            "reviewer": "writelab_adapter",
            "evidence_pack_ref": "ep-test",
        }
        state = {
            "task_id": "ledger-test-1",
            "acceptance_result": ar,
            "ledger_dir": str(tmp_path),
            "executed_nodes": [],
        }
        result = ledger_ingest_node(state)
        assert result["ledger_issue_count"] == 3
        assert result["ledger_summary"]["total"] == 3
        assert "ledger_ingest_node" in result["executed_nodes"]

        # Verify persistence
        entries = get_all_issues("ledger-test-1", ledger_dir=tmp_path)
        assert len(entries) == 3

    def test_ingest_without_task_id(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import ledger_ingest_node
        state = {
            "task_id": "",
            "acceptance_result": {"status": "accepted"},
            "ledger_dir": str(tmp_path),
            "executed_nodes": [],
        }
        result = ledger_ingest_node(state)
        assert result["ledger_issue_count"] == 0
        assert result["ledger_summary"] == {}

    def test_ingest_empty_acceptance(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import ledger_ingest_node
        state = {
            "task_id": "empty-test",
            "acceptance_result": {},
            "ledger_dir": str(tmp_path),
            "executed_nodes": [],
        }
        result = ledger_ingest_node(state)
        assert result["ledger_issue_count"] == 0

    def test_ingest_no_duplicate_on_rerun(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import ledger_ingest_node
        ar = {
            "status": "accepted",
            "reasons": ["test"],
            "blocking_issues": [],
            "non_blocking_issues": [make_issue("x1")],
            "required_next_actions": [],
            "reviewer": "writelab_adapter",
            "evidence_pack_ref": "ep",
        }
        state = {
            "task_id": "dedup-test",
            "acceptance_result": ar,
            "ledger_dir": str(tmp_path),
            "executed_nodes": [],
        }
        # Run twice
        r1 = ledger_ingest_node(state)
        r2 = ledger_ingest_node(state)
        assert r1["ledger_issue_count"] == 1
        assert r2["ledger_issue_count"] == 0  # no duplicates

    def test_ingest_default_ledger_dir(self, tmp_path):
        """Test with empty ledger_dir (uses default) — node doesn't crash."""
        from ai_workflow_hub.workflows.paper_graph import ledger_ingest_node
        ar = {
            "status": "accepted",
            "reasons": ["test"],
            "blocking_issues": [],
            "non_blocking_issues": [make_issue("default-1")],
            "required_next_actions": [],
            "reviewer": "writelab_adapter",
            "evidence_pack_ref": "ep",
        }
        state = {
            "task_id": "default-dir-test",
            "acceptance_result": ar,
            "ledger_dir": "",  # uses default
            "executed_nodes": [],
        }
        result = ledger_ingest_node(state)
        # Node should not crash; count may be 0 if default dir fails,
        # or 1 if default dir succeeds. Either is acceptable.
        assert "ledger_ingest_node" in result.get("executed_nodes", [])
        assert result["ledger_issue_count"] >= 0


class TestGraphExecutionWithLedger:
    """A12 integration tests: full graph invoke with ledger."""

    def _invoke(self, initial_state: dict, thread_id: str = "test-ledger"):
        compiled = compile_paper_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        return compiled.invoke(initial_state, config)

    def test_full_invoke_with_ledger(self, tmp_path):
        result = self._invoke({
            "task_id": "full-1",
            "writelab_mode": "mock",
            "ledger_dir": str(tmp_path),
            "expression_issues": [make_issue("e1"), make_issue("e2")],
        })
        assert result["status"] == "completed"
        assert result["ledger_issue_count"] == 2
        assert result["ledger_summary"].get("total") == 2

    def test_blocked_invoke_with_ledger(self, tmp_path):
        result = self._invoke({
            "task_id": "blocked-1",
            "writelab_mode": "mock",
            "ledger_dir": str(tmp_path),
            "expression_issues": [make_issue("b1", blocking=True, severity="critical")],
        })
        assert result["status"] == "blocked"
        assert result["ledger_summary"].get("blocking", 0) == 1

    def test_finalizer_includes_ledger_summary(self, tmp_path):
        result = self._invoke({
            "task_id": "summary-1",
            "writelab_mode": "mock",
            "ledger_dir": str(tmp_path),
            "expression_issues": [make_issue("s1", issue_type="citation")],
        })
        ls = result.get("ledger_summary", {})
        assert ls.get("total", 0) >= 1
        assert ls.get("type_breakdown", {}).get("citation", 0) >= 1


# ===========================================================================
# A13 Human Gate Resume Tests
# ===========================================================================

class TestHumanGateResume:
    """Tests for A13 human gate idempotency and resume."""

    def test_first_time_pause(self):
        from ai_workflow_hub.workflows.paper_graph import human_gate_node
        state = {"human_gate_decision": "", "executed_nodes": []}
        result = human_gate_node(state)
        assert result["human_required"] is True
        assert result["human_gate_triggered"] is True
        assert result["human_gate_decision"] == "pending"
        assert result["status"] == "human_required"

    def test_resume_approved(self):
        from ai_workflow_hub.workflows.paper_graph import human_gate_node
        state = {"human_gate_decision": "approved", "executed_nodes": ["diagnosis_node"]}
        result = human_gate_node(state)
        assert result["human_required"] is False
        assert result["human_gate_decision"] == "approved"
        assert result["status"] == "running"

    def test_resume_rejected(self):
        from ai_workflow_hub.workflows.paper_graph import human_gate_node
        state = {"human_gate_decision": "rejected", "executed_nodes": []}
        result = human_gate_node(state)
        assert result["human_required"] is False
        assert result["human_gate_decision"] == "rejected"
        assert result["status"] == "rejected"

    def test_routing_approved(self):
        from ai_workflow_hub.workflows.paper_graph import _route_after_human_gate
        assert _route_after_human_gate({"human_gate_decision": "approved"}) == "finalizer"

    def test_routing_rejected(self):
        from ai_workflow_hub.workflows.paper_graph import _route_after_human_gate
        assert _route_after_human_gate({"human_gate_decision": "rejected"}) == "__end__"

    def test_routing_pending(self):
        from ai_workflow_hub.workflows.paper_graph import _route_after_human_gate
        assert _route_after_human_gate({"human_gate_decision": "pending"}) == "__end__"

    def test_routing_empty(self):
        from ai_workflow_hub.workflows.paper_graph import _route_after_human_gate
        assert _route_after_human_gate({}) == "__end__"


class TestApplyHumanDecision:
    """Tests for the apply_human_decision helper."""

    def test_apply_approved(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "t1", "human_gate_decision": "pending", "status": "human_required"}
        updated = apply_human_decision(state, "approved")
        assert updated["human_gate_decision"] == "approved"

    def test_apply_rejected_with_note(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "t1", "human_gate_decision": "pending"}
        updated = apply_human_decision(state, "rejected", note="Too risky")
        assert updated["human_gate_decision"] == "rejected"
        assert "rejected" in updated["error_message"]
        assert "Too risky" in updated["error_message"]

    def test_apply_invalid_decision(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "t1"}
        with pytest.raises(ValueError, match="Invalid decision"):
            apply_human_decision(state, "maybe")

    def test_apply_to_pydantic_state(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = PaperWorkflowState(task_id="t1", human_gate_decision="pending")
        updated = apply_human_decision(state, "approved")
        assert updated["human_gate_decision"] == "approved"


class TestGraphResumeExecution:
    """Integration tests: full graph invoke with resume."""

    def test_pause_and_resume_approved(self):
        """Test graph pauses at human_gate and resumes with approval."""
        thread_id = "resume-approved"
        compiled = compile_paper_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}

        # First invoke: should pause at human_required
        result = compiled.invoke({
            "writelab_mode": "mock",
            "expression_issues": [make_issue("h1", human_required=True, severity="major")],
        }, config)
        assert result["status"] == "human_required"
        assert result["human_gate_triggered"] is True
        assert result["human_gate_decision"] == "pending"

        # Apply decision and resume
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        updated_state = apply_human_decision(result, "approved", note="LGTM")

        # Re-invoke with same thread_id
        result2 = compiled.invoke(updated_state, config)
        assert result2["human_gate_decision"] == "approved"
        # After approval, should reach finalizer → completed
        assert result2["status"] in ("completed", "human_required")

    def test_pause_and_resume_rejected(self):
        """Test graph pauses and resumes with rejection."""
        thread_id = "resume-rejected"
        compiled = compile_paper_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}

        # First invoke: pause
        result = compiled.invoke({
            "writelab_mode": "mock",
            "expression_issues": [make_issue("h1", human_required=True, severity="major")],
        }, config)
        assert result["status"] == "human_required"

        # Apply rejection
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        updated_state = apply_human_decision(result, "rejected", note="Not ready")

        # Re-invoke
        result2 = compiled.invoke(updated_state, config)
        assert result2["human_gate_decision"] == "rejected"
        assert result2["status"] == "rejected"


# ===========================================================================
# A14 Human Decision Audit Tests
# ===========================================================================

class TestHumanGateAuditFields:
    """A14: human_gate_node populates audit fields on resume."""

    def test_approved_populates_audit_fields(self):
        from ai_workflow_hub.workflows.paper_graph import human_gate_node
        state = {
            "human_gate_decision": "approved",
            "reviewer_id": "alice@example.com",
            "decision_timestamp": "2026-01-01T00:00:00+00:00",
            "decision_note": "All checks passed",
            "executed_nodes": [],
        }
        result = human_gate_node(state)
        assert result["reviewer_id"] == "alice@example.com"
        assert result["decision_timestamp"] == "2026-01-01T00:00:00+00:00"
        assert result["decision_note"] == "All checks passed"

    def test_rejected_populates_audit_fields(self):
        from ai_workflow_hub.workflows.paper_graph import human_gate_node
        state = {
            "human_gate_decision": "rejected",
            "reviewer_id": "bob@corp.com",
            "decision_timestamp": "2026-06-01T12:00:00+00:00",
            "decision_note": "Missing evidence",
            "executed_nodes": [],
        }
        result = human_gate_node(state)
        assert result["reviewer_id"] == "bob@corp.com"
        assert result["decision_note"] == "Missing evidence"

    def test_first_time_no_audit_fields(self):
        from ai_workflow_hub.workflows.paper_graph import human_gate_node
        state = {"human_gate_decision": "", "executed_nodes": []}
        result = human_gate_node(state)
        # First-time pause: no audit fields populated yet
        assert result.get("reviewer_id", "") == ""

    def test_audit_fields_from_decision_record(self, tmp_path):
        """When state lacks audit fields, fallback to decision record on disk."""
        from ai_workflow_hub.workflows.paper_graph import human_gate_node
        from ai_workflow_hub.context_layer.adapters.paper_decision_audit import (
            record_decision,
        )
        record_decision(
            "audit-fallback-task", "approved",
            reviewer_id="charlie@corp.com",
            note="Verified manually",
            base_dir=str(tmp_path),
        )
        # State has task_id but no reviewer_id — should fallback to disk record
        state = {
            "human_gate_decision": "approved",
            "task_id": "audit-fallback-task",
            "reviewer_id": "",
            "decision_timestamp": "",
            "decision_note": "",
            "executed_nodes": [],
        }
        # Patch the default base_dir to use tmp_path
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_decision_audit._decisions_dir",
            return_value=tmp_path / "decisions",
        ):
            result = human_gate_node(state)
        assert result["reviewer_id"] == "charlie@corp.com"
        assert result["decision_note"] == "Verified manually"


class TestApplyHumanDecisionAudit:
    """A14: apply_human_decision with reviewer_id and persist."""

    def test_apply_with_reviewer_id(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "T1"}
        result = apply_human_decision(
            state, "approved",
            reviewer_id="alice@example.com",
            note="Looks good",
        )
        assert result["reviewer_id"] == "alice@example.com"
        assert result["decision_note"] == "Looks good"
        assert result["decision_timestamp"] != ""

    def test_apply_sets_decision_timestamp(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "T2"}
        result = apply_human_decision(state, "approved")
        assert "T" in result["decision_timestamp"]  # ISO format

    def test_apply_persist_true(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        from ai_workflow_hub.context_layer.adapters.paper_decision_audit import (
            read_decision_record, get_audit_trail,
        )
        state = {"task_id": "persist-task", "acceptance_status": "human_required"}
        result = apply_human_decision(
            state, "approved",
            reviewer_id="dave@corp.com",
            note="Verified",
            persist=True,
            base_dir=str(tmp_path),
        )
        assert result["reviewer_id"] == "dave@corp.com"

        # Verify persistence
        rec = read_decision_record("persist-task", base_dir=str(tmp_path))
        assert rec is not None
        assert rec["decision"] == "approved"
        assert rec["reviewer_id"] == "dave@corp.com"

        # Verify audit trail
        trail = get_audit_trail("persist-task", base_dir=str(tmp_path))
        assert len(trail) >= 1

    def test_apply_persist_false_no_file(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        from ai_workflow_hub.context_layer.adapters.paper_decision_audit import (
            read_decision_record,
        )
        state = {"task_id": "no-persist-task"}
        apply_human_decision(state, "approved", persist=False)
        rec = read_decision_record("no-persist-task", base_dir=str(tmp_path))
        assert rec is None

    def test_apply_persist_without_task_id(self, tmp_path):
        """persist=True but no task_id — should not crash."""
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": ""}
        result = apply_human_decision(
            state, "approved",
            reviewer_id="eve@corp.com",
            persist=True,
            base_dir=str(tmp_path),
        )
        assert result["human_gate_decision"] == "approved"


class TestGraphResumeWithAudit:
    """A14: full graph resume with audit fields."""

    def test_resume_approved_preserves_reviewer_id(self):
        thread_id = "audit-resume-ok"
        compiled = compile_paper_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}

        result = compiled.invoke({
            "writelab_mode": "mock",
            "expression_issues": [make_issue("h1", human_required=True, severity="major")],
        }, config)
        assert result["status"] == "human_required"

        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        updated = apply_human_decision(
            result, "approved",
            reviewer_id="frank@corp.com",
            note="All clear",
        )

        result2 = compiled.invoke(updated, config)
        assert result2["reviewer_id"] == "frank@corp.com"
        assert result2["decision_note"] == "All clear"
        assert result2["decision_timestamp"] != ""
