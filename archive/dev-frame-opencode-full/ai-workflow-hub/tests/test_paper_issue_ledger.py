"""Tests for A11: Paper Issue Ledger.

Covers:
  - Ingestion from PaperReviewIssue lists and acceptance results
  - Query functions (get_all, get_open, blocking_count, critical_count, is_clear)
  - Summary generation
  - Status updates (resolve, wontfix, accepted_risk, mitigated, obsolete, reopen)
  - Batch operations (resolve_all, delete_ledger)
  - Pattern learning (issue_type_frequency)
  - Prompt context building
  - Edge cases (empty ledger, duplicate IDs, invalid status)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_workflow_hub.context_layer.adapters.paper_issue_ledger import (
    ingest_issues,
    get_all_issues,
    get_open_issues,
    blocking_count,
    critical_count,
    is_clear,
    ledger_summary,
    update_issue_status,
    mark_resolved,
    mark_wontfix,
    mark_accepted_risk,
    mark_mitigated,
    mark_obsolete,
    reopen_issue,
    resolve_all,
    delete_ledger,
    issue_type_frequency,
    build_prompt_context,
    ingest_from_acceptance_result,
    _load,
    _save,
    VALID_STATUSES,
    RESOLVED_STATUSES,
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
    recommendation: str = "fix it",
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


def make_acceptance_result(
    blocking_issues=None,
    non_blocking_issues=None,
    reviewer="writelab_adapter",
    ref="ep-001",
) -> dict[str, Any]:
    return {
        "status": "blocked" if blocking_issues else "accepted",
        "reasons": ["test"],
        "blocking_issues": blocking_issues or [],
        "non_blocking_issues": non_blocking_issues or [],
        "required_next_actions": [],
        "reviewer": reviewer,
        "evidence_pack_ref": ref,
    }


# ===========================================================================
# Ingestion Tests
# ===========================================================================

class TestIngestion:
    """Tests for issue ingestion."""

    def test_ingest_empty_list(self, tmp_path):
        added = ingest_issues("task-1", [], ledger_dir=tmp_path)
        assert added == 0
        assert get_all_issues("task-1", ledger_dir=tmp_path) == []

    def test_ingest_single_issue(self, tmp_path):
        added = ingest_issues(
            "task-1", [make_issue("issue-1")], ledger_dir=tmp_path
        )
        assert added == 1
        entries = get_all_issues("task-1", ledger_dir=tmp_path)
        assert len(entries) == 1
        assert entries[0]["issue_id"] == "issue-1"
        assert entries[0]["status"] == "open"

    def test_ingest_multiple_issues(self, tmp_path):
        issues = [make_issue(f"issue-{i}") for i in range(5)]
        added = ingest_issues("task-1", issues, ledger_dir=tmp_path)
        assert added == 5

    def test_ingest_no_duplicates(self, tmp_path):
        issue = make_issue("dup-1")
        ingest_issues("task-1", [issue], ledger_dir=tmp_path)
        added = ingest_issues("task-1", [issue], ledger_dir=tmp_path)
        assert added == 0
        assert len(get_all_issues("task-1", ledger_dir=tmp_path)) == 1

    def test_ingest_partial_overlap(self, tmp_path):
        ingest_issues("task-1", [make_issue("a"), make_issue("b")], ledger_dir=tmp_path)
        added = ingest_issues("task-1", [make_issue("b"), make_issue("c")], ledger_dir=tmp_path)
        assert added == 1
        assert len(get_all_issues("task-1", ledger_dir=tmp_path)) == 3

    def test_ingest_preserves_fields(self, tmp_path):
        issue = make_issue(
            "full-1", issue_type="citation", severity="critical",
            blocking=True, human_required=True, recommendation="add refs",
        )
        ingest_issues("task-1", [issue], source="gpt", evidence_pack_ref="ep-1",
                      ledger_dir=tmp_path)
        entry = get_all_issues("task-1", ledger_dir=tmp_path)[0]
        assert entry["issue_type"] == "citation"
        assert entry["severity"] == "critical"
        assert entry["blocking"] is True
        assert entry["human_required"] is True
        assert entry["recommendation"] == "add refs"
        assert entry["source"] == "gpt"
        assert entry["evidence_pack_ref"] == "ep-1"

    def test_ingest_skips_empty_issue_id(self, tmp_path):
        added = ingest_issues("task-1", [make_issue("")], ledger_dir=tmp_path)
        assert added == 0

    def test_ingest_from_acceptance_result(self, tmp_path):
        ar = make_acceptance_result(
            blocking_issues=[make_issue("b1", blocking=True, severity="critical")],
            non_blocking_issues=[make_issue("nb1"), make_issue("nb2")],
        )
        added = ingest_from_acceptance_result("task-ar", ar, ledger_dir=tmp_path)
        assert added == 3
        entries = get_all_issues("task-ar", ledger_dir=tmp_path)
        assert entries[0]["source"] == "writelab_adapter"
        assert entries[0]["evidence_pack_ref"] == "ep-001"


# ===========================================================================
# Query Tests
# ===========================================================================

class TestQuery:
    """Tests for issue query functions."""

    def setup_method(self, method):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())

    def _seed(self, task_id="q1"):
        issues = [
            make_issue("b1", blocking=True, severity="critical"),
            make_issue("b2", blocking=True, severity="major"),
            make_issue("nb1", severity="minor"),
            make_issue("nb2", severity="info"),
        ]
        ingest_issues(task_id, issues, ledger_dir=self.tmp)

    def test_get_all_issues(self):
        self._seed()
        assert len(get_all_issues("q1", ledger_dir=self.tmp)) == 4

    def test_get_open_issues(self):
        self._seed()
        assert len(get_open_issues("q1", ledger_dir=self.tmp)) == 4
        mark_resolved("q1", "b1", ledger_dir=self.tmp)
        assert len(get_open_issues("q1", ledger_dir=self.tmp)) == 3

    def test_blocking_count(self):
        self._seed()
        assert blocking_count("q1", ledger_dir=self.tmp) == 2
        mark_resolved("q1", "b1", ledger_dir=self.tmp)
        assert blocking_count("q1", ledger_dir=self.tmp) == 1

    def test_critical_count(self):
        self._seed()
        assert critical_count("q1", ledger_dir=self.tmp) == 1
        mark_resolved("q1", "b1", ledger_dir=self.tmp)
        assert critical_count("q1", ledger_dir=self.tmp) == 0

    def test_is_clear_empty(self):
        assert is_clear("empty-task", ledger_dir=self.tmp) is True

    def test_is_clear_with_blocking(self):
        self._seed()
        assert is_clear("q1", ledger_dir=self.tmp) is False

    def test_is_clear_all_resolved(self):
        self._seed()
        resolve_all("q1", ledger_dir=self.tmp)
        assert is_clear("q1", ledger_dir=self.tmp) is True

    def test_is_clear_non_blocking_only(self):
        ingest_issues("q2", [make_issue("nb1"), make_issue("nb2")], ledger_dir=self.tmp)
        assert is_clear("q2", ledger_dir=self.tmp) is True

    def test_empty_ledger(self):
        assert get_all_issues("nonexistent", ledger_dir=self.tmp) == []
        assert blocking_count("nonexistent", ledger_dir=self.tmp) == 0


# ===========================================================================
# Summary Tests
# ===========================================================================

class TestSummary:
    """Tests for ledger_summary."""

    def test_summary_empty(self, tmp_path):
        s = ledger_summary("empty", ledger_dir=tmp_path)
        assert s["total"] == 0
        assert s["open"] == 0
        assert s["blocking"] == 0

    def test_summary_with_issues(self, tmp_path):
        issues = [
            make_issue("b1", blocking=True, severity="critical", issue_type="privacy"),
            make_issue("nb1", issue_type="citation", severity="minor"),
            make_issue("nb2", issue_type="expression", severity="info"),
        ]
        ingest_issues("s1", issues, ledger_dir=tmp_path)
        mark_resolved("s1", "nb1", ledger_dir=tmp_path)

        s = ledger_summary("s1", ledger_dir=tmp_path)
        assert s["total"] == 3
        assert s["open"] == 2
        assert s["resolved"] == 1
        assert s["blocking"] == 1
        assert s["critical"] == 1
        assert s["severity_breakdown"]["critical"] == 1
        # nb1 (citation) resolved; remaining open: b1 (privacy) + nb2 (expression)
        assert s["type_breakdown"]["expression"] == 1
        assert s["type_breakdown"]["privacy"] == 1

    def test_summary_human_required(self, tmp_path):
        issues = [make_issue("h1", human_required=True)]
        ingest_issues("s2", issues, ledger_dir=tmp_path)
        s = ledger_summary("s2", ledger_dir=tmp_path)
        assert s["human_required"] == 1


# ===========================================================================
# Status Update Tests
# ===========================================================================

class TestStatusUpdates:
    """Tests for status update functions."""

    def setup_method(self, method):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        ingest_issues("t1", [make_issue("i1"), make_issue("i2")], ledger_dir=self.tmp)

    def test_mark_resolved(self):
        assert mark_resolved("t1", "i1", ledger_dir=self.tmp) is True
        entries = get_all_issues("t1", ledger_dir=self.tmp)
        assert entries[0]["status"] == "resolved"
        assert entries[0]["resolution_note"] == ""

    def test_mark_resolved_with_note(self):
        mark_resolved("t1", "i1", note="Fixed in v2", ledger_dir=self.tmp)
        entries = get_all_issues("t1", ledger_dir=self.tmp)
        assert entries[0]["resolution_note"] == "Fixed in v2"

    def test_mark_wontfix(self):
        assert mark_wontfix("t1", "i1", ledger_dir=self.tmp) is True
        assert get_all_issues("t1", ledger_dir=self.tmp)[0]["status"] == "wontfix"

    def test_mark_accepted_risk(self):
        assert mark_accepted_risk("t1", "i1", ledger_dir=self.tmp) is True
        assert get_all_issues("t1", ledger_dir=self.tmp)[0]["status"] == "accepted_risk"

    def test_mark_mitigated(self):
        assert mark_mitigated("t1", "i1", ledger_dir=self.tmp) is True
        assert get_all_issues("t1", ledger_dir=self.tmp)[0]["status"] == "mitigated"

    def test_mark_obsolete(self):
        assert mark_obsolete("t1", "i1", ledger_dir=self.tmp) is True
        assert get_all_issues("t1", ledger_dir=self.tmp)[0]["status"] == "obsolete"

    def test_reopen_issue(self):
        mark_resolved("t1", "i1", ledger_dir=self.tmp)
        assert reopen_issue("t1", "i1", ledger_dir=self.tmp) is True
        assert get_all_issues("t1", ledger_dir=self.tmp)[0]["status"] == "open"

    def test_update_nonexistent_issue(self):
        assert mark_resolved("t1", "nonexistent", ledger_dir=self.tmp) is False

    def test_update_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid status"):
            update_issue_status("t1", "i1", "invalid_status", ledger_dir=self.tmp)

    def test_updated_at_changes(self):
        entries_before = get_all_issues("t1", ledger_dir=self.tmp)
        ts_before = entries_before[0]["updated_at"]
        import time; time.sleep(0.01)
        mark_resolved("t1", "i1", ledger_dir=self.tmp)
        entries_after = get_all_issues("t1", ledger_dir=self.tmp)
        assert entries_after[0]["updated_at"] >= ts_before


# ===========================================================================
# Batch Operation Tests
# ===========================================================================

class TestBatchOperations:
    """Tests for resolve_all and delete_ledger."""

    def test_resolve_all(self, tmp_path):
        issues = [make_issue(f"i{i}") for i in range(5)]
        ingest_issues("b1", issues, ledger_dir=tmp_path)
        count = resolve_all("b1", ledger_dir=tmp_path)
        assert count == 5
        assert get_open_issues("b1", ledger_dir=tmp_path) == []

    def test_resolve_all_partial(self, tmp_path):
        issues = [make_issue(f"i{i}") for i in range(5)]
        ingest_issues("b2", issues, ledger_dir=tmp_path)
        mark_resolved("b2", "i0", ledger_dir=tmp_path)
        count = resolve_all("b2", ledger_dir=tmp_path)
        assert count == 4

    def test_resolve_all_invalid_status(self, tmp_path):
        with pytest.raises(ValueError):
            resolve_all("b1", status="open", ledger_dir=tmp_path)

    def test_delete_ledger(self, tmp_path):
        ingest_issues("del1", [make_issue("d1")], ledger_dir=tmp_path)
        assert delete_ledger("del1", ledger_dir=tmp_path) is True
        assert get_all_issues("del1", ledger_dir=tmp_path) == []

    def test_delete_nonexistent(self, tmp_path):
        assert delete_ledger("nonexistent", ledger_dir=tmp_path) is False


# ===========================================================================
# Learning / Pattern Tests
# ===========================================================================

class TestLearning:
    """Tests for issue_type_frequency and build_prompt_context."""

    def test_frequency_empty(self, tmp_path):
        freq = issue_type_frequency("empty", ledger_dir=tmp_path)
        assert freq == {}

    def test_frequency_counts(self, tmp_path):
        issues = [
            make_issue("e1", issue_type="expression"),
            make_issue("e2", issue_type="expression"),
            make_issue("c1", issue_type="citation"),
        ]
        ingest_issues("freq1", issues, ledger_dir=tmp_path)
        mark_resolved("freq1", "e1", ledger_dir=tmp_path)

        freq = issue_type_frequency("freq1", ledger_dir=tmp_path)
        assert freq["expression"]["total"] == 2
        assert freq["expression"]["resolved"] == 1
        assert freq["expression"]["open"] == 1
        assert freq["citation"]["total"] == 1
        assert freq["citation"]["open"] == 1

    def test_prompt_context_empty(self, tmp_path):
        ctx = build_prompt_context("empty", ledger_dir=tmp_path)
        assert ctx == ""

    def test_prompt_context_with_blocking(self, tmp_path):
        issues = [
            make_issue("b1", blocking=True, severity="critical", evidence="bad code"),
            make_issue("nb1", severity="minor"),
        ]
        ingest_issues("ctx1", issues, ledger_dir=tmp_path)
        ctx = build_prompt_context("ctx1", ledger_dir=tmp_path)
        assert "Unresolved Blocking" in ctx
        assert "b1" in ctx
        assert "Issue Type Frequency" in ctx

    def test_prompt_context_no_blocking(self, tmp_path):
        issues = [make_issue("nb1", severity="minor")]
        ingest_issues("ctx2", issues, ledger_dir=tmp_path)
        ctx = build_prompt_context("ctx2", ledger_dir=tmp_path)
        assert "Unresolved Blocking" not in ctx
        assert "Issue Type Frequency" in ctx

    def test_prompt_context_max_lines(self, tmp_path):
        issues = [
            make_issue(f"b{i}", blocking=True, severity="critical")
            for i in range(30)
        ]
        ingest_issues("ctx3", issues, ledger_dir=tmp_path)
        ctx = build_prompt_context("ctx3", ledger_dir=tmp_path, max_lines=5)
        lines = ctx.split("\n")
        # Should have header + 5 issues + "and N more" line + freq header + freq lines
        assert "25 more" in ctx


# ===========================================================================
# Integration Tests
# ===========================================================================

class TestIntegration:
    """Integration tests with A8 acceptance results."""

    def test_full_lifecycle(self, tmp_path):
        # 1. Create acceptance result with issues
        ar = make_acceptance_result(
            blocking_issues=[
                make_issue("b1", blocking=True, severity="critical", issue_type="privacy"),
            ],
            non_blocking_issues=[
                make_issue("nb1", severity="minor", issue_type="expression"),
                make_issue("nb2", severity="info", issue_type="citation"),
            ],
        )

        # 2. Ingest
        added = ingest_from_acceptance_result("lifecycle-1", ar, ledger_dir=tmp_path)
        assert added == 3
        assert not is_clear("lifecycle-1", ledger_dir=tmp_path)

        # 3. Resolve blocking issue
        mark_resolved("lifecycle-1", "b1", note="Privacy fixed", ledger_dir=tmp_path)
        assert blocking_count("lifecycle-1", ledger_dir=tmp_path) == 0
        assert is_clear("lifecycle-1", ledger_dir=tmp_path)

        # 4. Check summary
        s = ledger_summary("lifecycle-1", ledger_dir=tmp_path)
        assert s["total"] == 3
        assert s["open"] == 2
        assert s["resolved"] == 1

        # 5. Build prompt context
        ctx = build_prompt_context("lifecycle-1", ledger_dir=tmp_path)
        assert "Unresolved Blocking" not in ctx  # b1 resolved
        assert "expression" in ctx

    def test_multi_source_ingestion(self, tmp_path):
        # Ingest from writelab_adapter
        ar1 = make_acceptance_result(
            non_blocking_issues=[make_issue("wl-1")],
            reviewer="writelab_adapter",
        )
        ingest_from_acceptance_result("multi-1", ar1, ledger_dir=tmp_path)

        # Ingest from gpt
        ar2 = make_acceptance_result(
            non_blocking_issues=[make_issue("gpt-1")],
            reviewer="gpt",
            ref="ep-gpt",
        )
        ingest_from_acceptance_result("multi-1", ar2, ledger_dir=tmp_path)

        entries = get_all_issues("multi-1", ledger_dir=tmp_path)
        assert len(entries) == 2
        sources = {e["source"] for e in entries}
        assert "writelab_adapter" in sources
        assert "gpt" in sources


# ===========================================================================
# Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_load_corrupted_json(self, tmp_path):
        fp = tmp_path / "corrupt.json"
        fp.write_text("{invalid json", encoding="utf-8")
        # _load should return empty list for corrupted files
        # Use the internal function with task_id that maps to this file
        from ai_workflow_hub.context_layer.adapters.paper_issue_ledger import _ledger_path
        # Create a task whose ledger file is the corrupted one
        task_id = "corrupt"
        ledger_file = _ledger_path(task_id, tmp_path)
        ledger_file.write_text("{not valid", encoding="utf-8")
        result = get_all_issues(task_id, ledger_dir=tmp_path)
        assert result == []

    def test_concurrent_ingestion_idempotent(self, tmp_path):
        """Multiple ingestions of same issues should be idempotent."""
        issues = [make_issue("c1"), make_issue("c2")]
        for _ in range(5):
            ingest_issues("concurrent", issues, ledger_dir=tmp_path)
        assert len(get_all_issues("concurrent", ledger_dir=tmp_path)) == 2

    def test_all_valid_statuses(self):
        assert "open" in VALID_STATUSES
        assert "resolved" in VALID_STATUSES
        assert "wontfix" in VALID_STATUSES
        assert "accepted_risk" in VALID_STATUSES
        assert "mitigated" in VALID_STATUSES
        assert "obsolete" in VALID_STATUSES

    def test_resolved_statuses(self):
        assert "open" not in RESOLVED_STATUSES
        for s in ("resolved", "wontfix", "accepted_risk", "mitigated", "obsolete"):
            assert s in RESOLVED_STATUSES

    def test_large_ledger(self, tmp_path):
        """Test with 500 issues."""
        issues = [make_issue(f"bulk-{i}", severity="minor") for i in range(500)]
        added = ingest_issues("bulk", issues, ledger_dir=tmp_path)
        assert added == 500
        assert len(get_all_issues("bulk", ledger_dir=tmp_path)) == 500
