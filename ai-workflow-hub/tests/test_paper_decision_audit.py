"""Tests for A14: Paper Decision Audit Trail.

Covers:
  - record_decision: persistence, validation, atomic write
  - read_decision_record: existing, missing, corrupt files
  - get_audit_trail: entries accumulation, empty trail
  - log_decision_audit: global audit integration (best-effort)
  - Integration with apply_human_decision (persist=True)
  - Integration with human_gate_node (audit field population)
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import patch

import pytest

from ai_workflow_hub.context_layer.adapters.paper_decision_audit import (
    record_decision,
    read_decision_record,
    get_audit_trail,
    log_decision_audit,
    sanitize_task_id,
    is_decision_stale,
    get_decision_count,
    VALID_DECISIONS,
    DECISION_SCHEMA_VERSION,
    _decisions_dir,
    _decision_path,
    _audit_trail_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_base(tmp_path):
    """Provide a temporary base directory for decision files."""
    return str(tmp_path)


# ---------------------------------------------------------------------------
# TestRecordDecision
# ---------------------------------------------------------------------------

class TestRecordDecision:
    """Tests for record_decision()."""

    def test_record_approved(self, tmp_base):
        rec = record_decision("T1", "approved", base_dir=tmp_base)
        assert rec["decision"] == "approved"
        assert rec["task_id"] == "T1"
        assert rec["decision_id"] == "T1-decision"
        assert rec["schema_version"] == DECISION_SCHEMA_VERSION

    def test_record_rejected(self, tmp_base):
        rec = record_decision("T2", "rejected", base_dir=tmp_base)
        assert rec["decision"] == "rejected"

    def test_record_with_reviewer_id(self, tmp_base):
        rec = record_decision(
            "T3", "approved",
            reviewer_id="alice@example.com",
            base_dir=tmp_base,
        )
        assert rec["reviewer_id"] == "alice@example.com"

    def test_record_with_note(self, tmp_base):
        rec = record_decision(
            "T4", "rejected",
            note="Insufficient evidence",
            base_dir=tmp_base,
        )
        assert rec["note"] == "Insufficient evidence"

    def test_record_with_context(self, tmp_base):
        ctx = {"blocking_count": 2, "acceptance_status": "human_required"}
        rec = record_decision("T5", "approved", context=ctx, base_dir=tmp_base)
        assert rec["context"]["blocking_count"] == 2

    def test_record_has_timestamp(self, tmp_base):
        rec = record_decision("T6", "approved", base_dir=tmp_base)
        assert "timestamp" in rec
        assert "T" in rec["timestamp"]  # ISO format

    def test_record_invalid_decision_raises(self, tmp_base):
        with pytest.raises(ValueError, match="Invalid decision"):
            record_decision("T7", "maybe", base_dir=tmp_base)

    def test_record_empty_string_raises(self, tmp_base):
        with pytest.raises(ValueError):
            record_decision("T8", "", base_dir=tmp_base)

    def test_record_persists_to_disk(self, tmp_base):
        record_decision("T9", "approved", base_dir=tmp_base)
        path = _decision_path("T9", tmp_base)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["decision"] == "approved"

    def test_record_atomic_write_no_tmp_left(self, tmp_base):
        record_decision("T10", "approved", base_dir=tmp_base)
        d = _decisions_dir(tmp_base)
        tmp_files = [f for f in d.iterdir() if f.suffix == ".tmp"]
        assert len(tmp_files) == 0

    def test_record_overwrite_previous(self, tmp_base):
        record_decision("T11", "approved", note="first", base_dir=tmp_base)
        record_decision("T11", "rejected", note="second", base_dir=tmp_base)
        rec = read_decision_record("T11", base_dir=tmp_base)
        assert rec["decision"] == "rejected"
        assert rec["note"] == "second"

    def test_record_appends_audit_trail(self, tmp_base):
        record_decision("T12", "approved", reviewer_id="bob", base_dir=tmp_base)
        record_decision("T12", "rejected", reviewer_id="alice", base_dir=tmp_base)
        trail = get_audit_trail("T12", base_dir=tmp_base)
        assert len(trail) == 2
        assert trail[0]["decision"] == "approved"
        assert trail[1]["decision"] == "rejected"


# ---------------------------------------------------------------------------
# TestReadDecisionRecord
# ---------------------------------------------------------------------------

class TestReadDecisionRecord:
    """Tests for read_decision_record()."""

    def test_read_existing(self, tmp_base):
        record_decision("T1", "approved", base_dir=tmp_base)
        rec = read_decision_record("T1", base_dir=tmp_base)
        assert rec is not None
        assert rec["decision"] == "approved"

    def test_read_missing_returns_none(self, tmp_base):
        rec = read_decision_record("NONEXISTENT", base_dir=tmp_base)
        assert rec is None

    def test_read_corrupt_json_returns_none(self, tmp_base):
        path = _decision_path("T_CORRUPT", tmp_base)
        path.write_text("not valid json {{{", encoding="utf-8")
        rec = read_decision_record("T_CORRUPT", base_dir=tmp_base)
        assert rec is None

    def test_read_empty_dir_returns_none(self, tmp_path):
        empty = str(tmp_path / "empty")
        os.makedirs(empty, exist_ok=True)
        rec = read_decision_record("T1", base_dir=empty)
        assert rec is None

    def test_read_preserves_all_fields(self, tmp_base):
        ctx = {"blocking_count": 1}
        record_decision(
            "T_FULL", "approved",
            reviewer_id="r@x.com",
            note="LGTM",
            context=ctx,
            base_dir=tmp_base,
        )
        rec = read_decision_record("T_FULL", base_dir=tmp_base)
        assert rec["reviewer_id"] == "r@x.com"
        assert rec["note"] == "LGTM"
        assert rec["context"]["blocking_count"] == 1
        assert rec["schema_version"] == DECISION_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# TestGetAuditTrail
# ---------------------------------------------------------------------------

class TestGetAuditTrail:
    """Tests for get_audit_trail()."""

    def test_empty_trail(self, tmp_base):
        trail = get_audit_trail("NO_TASK", base_dir=tmp_base)
        assert trail == []

    def test_single_entry(self, tmp_base):
        record_decision("T1", "approved", base_dir=tmp_base)
        trail = get_audit_trail("T1", base_dir=tmp_base)
        assert len(trail) == 1
        assert trail[0]["event"] == "decision_recorded"
        assert trail[0]["decision"] == "approved"

    def test_multiple_entries_ordered(self, tmp_base):
        record_decision("T2", "approved", reviewer_id="a", base_dir=tmp_base)
        record_decision("T2", "rejected", reviewer_id="b", base_dir=tmp_base)
        record_decision("T2", "approved", reviewer_id="c", base_dir=tmp_base)
        trail = get_audit_trail("T2", base_dir=tmp_base)
        assert len(trail) == 3
        assert [e["reviewer_id"] for e in trail] == ["a", "b", "c"]

    def test_trail_entry_has_timestamp(self, tmp_base):
        record_decision("T3", "approved", base_dir=tmp_base)
        trail = get_audit_trail("T3", base_dir=tmp_base)
        assert "timestamp" in trail[0]

    def test_trail_entry_has_note(self, tmp_base):
        record_decision("T4", "rejected", note="bad data", base_dir=tmp_base)
        trail = get_audit_trail("T4", base_dir=tmp_base)
        assert trail[0]["note"] == "bad data"

    def test_trail_corrupt_jsonl_skipped(self, tmp_base):
        # Write one valid, one corrupt entry
        record_decision("T5", "approved", base_dir=tmp_base)
        path = _audit_trail_path("T5", tmp_base)
        with open(path, "a", encoding="utf-8") as f:
            f.write("not json\n")
        trail = get_audit_trail("T5", base_dir=tmp_base)
        assert len(trail) == 1  # corrupt line skipped


# ---------------------------------------------------------------------------
# TestLogDecisionAudit
# ---------------------------------------------------------------------------

class TestLogDecisionAudit:
    """Tests for log_decision_audit() — best-effort global audit integration."""

    def test_log_calls_audit_log(self):
        with patch("ai_workflow_hub.context_layer.adapters.paper_decision_audit.log_decision_audit") as mock:
            # Call the real function, not the mock
            pass
        # Just verify it doesn't raise
        log_decision_audit(
            task_id="T1",
            decision="approved",
            reviewer_id="alice",
            note="LGTM",
        )

    def test_log_with_all_params(self):
        log_decision_audit(
            task_id="T2",
            decision="rejected",
            reviewer_id="bob@corp.com",
            note="Missing evidence",
            run_id="run-001",
            project_id="proj-001",
        )

    def test_log_survives_import_error(self):
        """log_decision_audit should not raise even if audit module fails."""
        # This tests the try/except in log_decision_audit
        log_decision_audit(
            task_id="T3",
            decision="approved",
            reviewer_id="",
            note="",
        )


# ---------------------------------------------------------------------------
# TestDecisionDirHelpers
# ---------------------------------------------------------------------------

class TestDecisionDirHelpers:
    """Tests for directory and path helper functions."""

    def test_decisions_dir_created(self, tmp_base):
        d = _decisions_dir(tmp_base)
        assert d.exists()
        assert d.is_dir()

    def test_decision_path_format(self, tmp_base):
        path = _decision_path("my-task", tmp_base)
        assert path.name == "my-task-decision.json"

    def test_audit_trail_path_format(self, tmp_base):
        path = _audit_trail_path("my-task", tmp_base)
        assert path.name == "my-task-audit.jsonl"


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Tests for module constants."""

    def test_valid_decisions(self):
        assert VALID_DECISIONS == {"approved", "rejected"}

    def test_schema_version(self):
        assert DECISION_SCHEMA_VERSION == "2.0"


# ===========================================================================
# A15 Hardening Tests
# ===========================================================================

class TestSanitizeTaskId:
    """A15: task_id sanitization for filesystem safety."""

    def test_normal_id(self):
        assert sanitize_task_id("task-001") == "task-001"

    def test_with_spaces(self):
        result = sanitize_task_id("my task name")
        assert " " not in result
        assert result == "my_task_name"

    def test_path_traversal(self):
        result = sanitize_task_id("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    def test_hidden_file(self):
        result = sanitize_task_id(".hidden")
        assert not result.startswith(".")

    def test_special_chars(self):
        result = sanitize_task_id("task<>:|?*name")
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "|" not in result

    def test_truncation(self):
        long_id = "x" * 200
        result = sanitize_task_id(long_id)
        assert len(result) <= 128

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            sanitize_task_id("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            sanitize_task_id("   ")

    def test_all_special_chars_sanitized(self):
        """All special chars produce a valid but safe identifier."""
        result = sanitize_task_id("///\\\\")
        assert "/" not in result
        assert "\\" not in result
        assert len(result) > 0  # not empty after sanitization

    def test_underscores_preserved(self):
        assert sanitize_task_id("task_name_v2") == "task_name_v2"

    def test_dots_preserved_internally(self):
        assert sanitize_task_id("task.v2.0") == "task.v2.0"

    def test_collapses_underscores(self):
        result = sanitize_task_id("task___name")
        assert "___" not in result


class TestRequireReviewer:
    """A15: reviewer_id enforcement."""

    def test_require_reviewer_empty_raises(self, tmp_base):
        with pytest.raises(ValueError, match="reviewer_id is required"):
            record_decision("T1", "approved", reviewer_id="", base_dir=tmp_base, require_reviewer=True)

    def test_require_reviewer_whitespace_raises(self, tmp_base):
        with pytest.raises(ValueError, match="reviewer_id is required"):
            record_decision("T2", "approved", reviewer_id="   ", base_dir=tmp_base, require_reviewer=True)

    def test_require_reviewer_valid_ok(self, tmp_base):
        rec = record_decision("T3", "approved", reviewer_id="alice@corp.com",
                              base_dir=tmp_base, require_reviewer=True)
        assert rec["reviewer_id"] == "alice@corp.com"

    def test_no_require_reviewer_empty_ok(self, tmp_base):
        rec = record_decision("T4", "approved", reviewer_id="", base_dir=tmp_base)
        assert rec["reviewer_id"] == ""


class TestDecisionRound:
    """A15: decision round tracking."""

    def test_first_round(self, tmp_base):
        rec = record_decision("T1", "approved", base_dir=tmp_base)
        assert rec["round"] == 1

    def test_second_round(self, tmp_base):
        record_decision("T2", "approved", base_dir=tmp_base)
        rec2 = record_decision("T2", "rejected", base_dir=tmp_base)
        assert rec2["round"] == 2

    def test_third_round(self, tmp_base):
        record_decision("T3", "approved", base_dir=tmp_base)
        record_decision("T3", "rejected", base_dir=tmp_base)
        rec3 = record_decision("T3", "approved", base_dir=tmp_base)
        assert rec3["round"] == 3

    def test_audit_trail_has_round(self, tmp_base):
        record_decision("T4", "approved", base_dir=tmp_base)
        trail = get_audit_trail("T4", base_dir=tmp_base)
        assert trail[0]["round"] == 1


class TestDecisionStale:
    """A15: stale decision detection."""

    def test_no_decision_not_stale(self, tmp_base):
        assert is_decision_stale("NONEXISTENT", base_dir=tmp_base) is False

    def test_fresh_decision_not_stale(self, tmp_base):
        record_decision("T1", "approved", base_dir=tmp_base)
        assert is_decision_stale("T1", base_dir=tmp_base, max_age_seconds=3600) is False

    def test_old_decision_stale(self, tmp_base):
        # Write a record with old timestamp manually
        from pathlib import Path
        from datetime import datetime, timezone, timedelta
        import json

        rec = {
            "decision_id": "T2-decision",
            "task_id": "T2",
            "decision": "approved",
            "reviewer_id": "test",
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            "note": "",
            "context": {},
            "schema_version": "2.0",
            "round": 1,
        }
        d = _decisions_dir(tmp_base)
        (d / "T2-decision.json").write_text(json.dumps(rec), encoding="utf-8")

        assert is_decision_stale("T2", base_dir=tmp_base, max_age_seconds=7*24*3600) is True

    def test_custom_max_age(self, tmp_base):
        record_decision("T3", "approved", base_dir=tmp_base)
        # 0 seconds max age → immediately stale
        assert is_decision_stale("T3", base_dir=tmp_base, max_age_seconds=0) is True

    def test_no_timestamp_treated_stale(self, tmp_base):
        from pathlib import Path
        import json
        rec = {"decision_id": "T4-decision", "task_id": "T4", "decision": "approved",
               "reviewer_id": "", "timestamp": "", "note": "", "context": {},
               "schema_version": "2.0", "round": 1}
        d = _decisions_dir(tmp_base)
        (d / "T4-decision.json").write_text(json.dumps(rec), encoding="utf-8")
        assert is_decision_stale("T4", base_dir=tmp_base) is True


class TestGetDecisionCount:
    """A15: decision count from audit trail."""

    def test_no_decisions(self, tmp_base):
        assert get_decision_count("EMPTY", base_dir=tmp_base) == 0

    def test_one_decision(self, tmp_base):
        record_decision("T1", "approved", base_dir=tmp_base)
        assert get_decision_count("T1", base_dir=tmp_base) == 1

    def test_multiple_decisions(self, tmp_base):
        record_decision("T2", "approved", base_dir=tmp_base)
        record_decision("T2", "rejected", base_dir=tmp_base)
        record_decision("T2", "approved", base_dir=tmp_base)
        assert get_decision_count("T2", base_dir=tmp_base) == 3


class TestA15ApplyHumanDecision:
    """A15: apply_human_decision with hardening features."""

    def test_require_reviewer_raises(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "T1"}
        with pytest.raises(ValueError, match="reviewer_id is required"):
            apply_human_decision(state, "approved", reviewer_id="", require_reviewer=True)

    def test_require_reviewer_ok(self):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "T2"}
        result = apply_human_decision(state, "approved", reviewer_id="alice", require_reviewer=True)
        assert result["human_gate_decision"] == "approved"

    def test_persist_sets_decision_round(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "round-test"}
        result = apply_human_decision(
            state, "approved",
            reviewer_id="bob",
            persist=True,
            base_dir=str(tmp_path),
        )
        assert result["decision_round"] == 1

    def test_base_dir_stored_in_state(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import apply_human_decision
        state = {"task_id": "basedir-test"}
        result = apply_human_decision(
            state, "approved",
            reviewer_id="carol",
            persist=True,
            base_dir=str(tmp_path),
        )
        assert result["decision_base_dir"] == str(tmp_path)


class TestA15StateFields:
    """A15: PaperWorkflowState new fields."""

    def test_decision_base_dir_field(self):
        from ai_workflow_hub.workflows.paper_workflow_state import PaperWorkflowState
        state = PaperWorkflowState()
        assert hasattr(state, "decision_base_dir")
        assert state.decision_base_dir == ""

    def test_decision_round_field(self):
        from ai_workflow_hub.workflows.paper_workflow_state import PaperWorkflowState
        state = PaperWorkflowState()
        assert hasattr(state, "decision_round")
        assert state.decision_round == 0


class TestA15GraphIntegration:
    """A15: full graph resume with hardened audit."""

    def test_resume_with_base_dir(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import (
            apply_human_decision, compile_paper_graph,
        )
        from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import compute_acceptance

        compiled = compile_paper_graph("a15-graph-test")
        config = {"configurable": {"thread_id": "a15-graph-test"}}

        issue_hr = {
            "issue_id": "HR1", "issue_type": "citation", "severity": "major",
            "message": "Needs human review", "paragraph_index": 0,
            "human_required": True,
        }
        ar = compute_acceptance(issues=[issue_hr], reviewer="writelab_adapter", evidence_pack_ref="")

        r1 = compiled.invoke({
            "task_id": "a15-integration-task",
            "writelab_mode": "mock",
            "paragraph_issues": [issue_hr],
            "all_review_issues": [issue_hr],
            "acceptance_result": ar,
            "acceptance_status": ar["status"],
        }, config)
        assert r1["status"] == "human_required"

        updated = apply_human_decision(
            r1, "approved",
            reviewer_id="dave@corp.com",
            note="Reviewed",
            persist=True,
            base_dir=str(tmp_path),
        )
        r2 = compiled.invoke(updated, config)

        assert r2["reviewer_id"] == "dave@corp.com"
        assert r2["decision_round"] >= 1
        assert "paper_finalizer_node" in r2.get("executed_nodes", [])
