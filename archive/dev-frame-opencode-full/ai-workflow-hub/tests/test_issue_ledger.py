"""Test issue ledger functionality."""
import json, tempfile, os
from pathlib import Path
import sys
sys.path.insert(0, 'src')
from ai_workflow_hub.issue_ledger import (
    unresolved_p0_count, ledger_summary, _load_ledger, _save_ledger,
    derive_issues_from_state, write_run_delta, mark_verified, mark_wontfix,
)

class TestIssueLedger:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def test_empty_ledger_returns_zero_p0(self):
        assert unresolved_p0_count(self.tmp) == 0

    def test_unresolved_p0_counted(self):
        issues = [
            {"id": "1", "priority": "P0", "status": "open"},
            {"id": "2", "priority": "P0", "status": "open"},
            {"id": "3", "priority": "P1", "status": "open"},
        ]
        _save_ledger(self.tmp, issues)
        assert unresolved_p0_count(self.tmp) == 2

    def test_resolved_p0_not_counted(self):
        issues = [
            {"id": "1", "priority": "P0", "status": "resolved"},
            {"id": "2", "priority": "P0", "status": "obsolete"},
        ]
        _save_ledger(self.tmp, issues)
        assert unresolved_p0_count(self.tmp) == 0

    def test_ledger_summary(self):
        issues = [
            {"id": "1", "priority": "P0", "status": "open"},
            {"id": "2", "priority": "P1", "status": "open"},
            {"id": "3", "priority": "P1", "status": "resolved"},
        ]
        _save_ledger(self.tmp, issues)
        s = ledger_summary(self.tmp)
        assert s["total"] == 3
        assert s["p0_unresolved"] == 1
        assert s["p1_unresolved"] == 1

    def test_derive_issues_from_error_state(self):
        state = {"error_message": "Something went wrong"}
        issues = derive_issues_from_state(state)
        assert len(issues) >= 1
        assert issues[0]["priority"] == "P1"

    def test_write_run_delta(self):
        write_run_delta(self.tmp, [{"id": "D1", "priority": "P0", "status": "open"}])
        assert len(_load_ledger(self.tmp)) == 1

    def test_mark_verified(self):
        _save_ledger(self.tmp, [{"id": "X1", "priority": "P0", "status": "open"}])
        mark_verified(self.tmp, "X1")
        issues = _load_ledger(self.tmp)
        assert issues[0]["status"] == "verified"
