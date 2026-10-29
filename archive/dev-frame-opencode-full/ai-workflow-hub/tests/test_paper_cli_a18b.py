"""test_paper_cli_a18b.py — A18B Privacy Hardening Tests.

Tests the A18B redaction fixes:
  - _redact_str handles JSON-quoted patterns ("field": "...")
  - _deep_redact recursively redacts sensitive keys in dicts/lists
  - paper ledger applies _redact_str to issue descriptions
  - paper ledger --json applies _deep_redact to issues
  - paper evidence --json applies _deep_redact to manifest
  - paper validate applies _redact_str to errors and reasons
  - paper validate --json applies _deep_redact to validation_errors
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ai_workflow_hub.cli import app, _redact_str, _deep_redact

runner = CliRunner()

_RT_PATH = "ai_workflow_hub.context_layer.adapters.paper_runtime"
_LEDGER_PATH = "ai_workflow_hub.context_layer.adapters.paper_issue_ledger"
_GATE_PATH = "ai_workflow_hub.context_layer.adapters.paper_acceptance_gate"


def _invoke(args: list[str]):
    with patch("ai_workflow_hub.cli.init_env"):
        return runner.invoke(app, args, catch_exceptions=False)


def _make_run_dir(base: Path, run_id: str, state: dict) -> Path:
    rd = base / run_id
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return rd


# ===========================================================================
# TestRedactStrJsonPatterns — A18B L2
# ===========================================================================

class TestRedactStrJsonPatterns:
    """_redact_str should handle JSON-quoted forms in addition to simple forms."""

    def test_json_quoted_string_value(self):
        """Should redact "paragraph_text": "secret" in JSON-like text."""
        text = '"paragraph_text": "secret content here"'
        result = _redact_str(text)
        assert "secret content here" not in result
        assert "[REDACTED]" in result

    def test_json_quoted_writelab_token(self):
        """Should redact "writelab_token": "tok-abc" in JSON-like text."""
        text = '"writelab_token": "tok-abc-123"'
        result = _redact_str(text)
        assert "tok-abc-123" not in result
        assert "[REDACTED]" in result

    def test_simple_pattern_still_works(self):
        """Original simple pattern should still work."""
        assert _redact_str("paragraph_text: some secret") == "paragraph_text: [REDACTED]"
        assert _redact_str("writelab_token=abc") == "writelab_token: [REDACTED]"

    def test_clean_text_unchanged(self):
        """Non-sensitive text should be unchanged."""
        text = "Issue: missing citation in section 3"
        assert _redact_str(text) == text

    def test_mixed_patterns(self):
        """Should handle text with both simple and JSON patterns."""
        text = 'Warning: paragraph_text: raw leak. Also "writelab_token": "key-123" found.'
        result = _redact_str(text)
        assert "raw leak" not in result
        assert "key-123" not in result


# ===========================================================================
# TestDeepRedact — A18B L2
# ===========================================================================

class TestDeepRedact:
    """_deep_redact should recursively redact sensitive keys in nested structures."""

    def test_simple_dict(self):
        obj = {"paragraph_text": "secret", "status": "ok"}
        result = _deep_redact(obj)
        assert result["paragraph_text"] == "[REDACTED]"
        assert result["status"] == "ok"

    def test_writelab_token_key(self):
        obj = {"writelab_token": "tok-secret-abc", "name": "test"}
        result = _deep_redact(obj)
        assert result["writelab_token"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_nested_dict(self):
        obj = {"data": {"paragraph_text": "deep secret", "other": "safe"}}
        result = _deep_redact(obj)
        assert result["data"]["paragraph_text"] == "[REDACTED]"
        assert result["data"]["other"] == "safe"

    def test_list_of_dicts(self):
        obj = [
            {"paragraph_text": "secret1", "id": 1},
            {"writelab_token": "secret2", "id": 2},
        ]
        result = _deep_redact(obj)
        assert result[0]["paragraph_text"] == "[REDACTED]"
        assert result[1]["writelab_token"] == "[REDACTED]"

    def test_string_values_redacted(self):
        """Strings containing sensitive patterns should be redacted."""
        obj = {"message": "paragraph_text: leaked value in error"}
        result = _deep_redact(obj)
        assert "leaked value" not in result["message"]

    def test_non_string_values_preserved(self):
        obj = {"count": 42, "flag": True, "ratio": 3.14}
        result = _deep_redact(obj)
        assert result == obj

    def test_empty_structures(self):
        assert _deep_redact({}) == {}
        assert _deep_redact([]) == []
        assert _deep_redact("") == ""


# ===========================================================================
# TestLedgerRedaction — A18B L3
# ===========================================================================

class TestLedgerRedaction:
    """paper ledger should redact issue descriptions containing sensitive data."""

    def test_ledger_table_redacts_descriptions(self, tmp_path):
        """Issue descriptions in Rich table should be redacted."""
        state = {"task_id": "TASK-R1", "status": "completed"}
        _make_run_dir(tmp_path, "paper-r1", state)
        mock_summary = {"task_id": "TASK-R1", "total": 1, "open": 1, "resolved": 0,
                        "blocking": 0, "critical": 0}
        mock_issues = [
            {"issue_id": "iss-01", "issue_type": "content", "severity": "minor",
             "status": "open",
             "description": "paragraph_text: sensitive manuscript excerpt leaked"},
        ]
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-r1"), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=mock_summary), \
             patch(f"{_LEDGER_PATH}.get_open_issues", return_value=mock_issues), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=True):
            result = _invoke(["paper", "ledger", "--run-id", "paper-r1"])
        assert result.exit_code == 0
        assert "sensitive manuscript excerpt leaked" not in result.output

    def test_ledger_json_redacts_issues(self, tmp_path):
        """JSON output should deep-redact issue list."""
        state = {"task_id": "TASK-R2", "status": "completed"}
        _make_run_dir(tmp_path, "paper-r2", state)
        mock_summary = {"task_id": "TASK-R2", "total": 1, "open": 1, "resolved": 0,
                        "blocking": 0, "critical": 0}
        mock_issues = [
            {"issue_id": "iss-02", "issue_type": "content", "severity": "major",
             "status": "open", "paragraph_text": "secret field in issue",
             "description": "normal description"},
        ]
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-r2"), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=mock_summary), \
             patch(f"{_LEDGER_PATH}.get_open_issues", return_value=mock_issues), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=True):
            result = _invoke(["paper", "ledger", "--run-id", "paper-r2", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["issues"][0]["paragraph_text"] == "[REDACTED]"
        assert parsed["issues"][0]["description"] == "normal description"


# ===========================================================================
# TestEvidenceRedaction — A18B L3
# ===========================================================================

class TestEvidenceRedaction:
    """paper evidence --json should deep-redact sensitive fields in manifest."""

    def test_evidence_json_redacts_sensitive_keys(self, tmp_path):
        state = {
            "task_id": "TASK-ER1", "status": "completed",
            "evidence_manifest": {
                "reviewer": "writelab_adapter",
                "manifest_status": "complete",
                "entries": [
                    {"source": "expr_01", "evidence_type": "expression",
                     "status": "ok", "paragraph_text": "secret manuscript text"},
                ],
            },
        }
        _make_run_dir(tmp_path, "paper-er1", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-er1"):
            result = _invoke(["paper", "evidence", "--run-id", "paper-er1", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["entries"][0]["paragraph_text"] == "[REDACTED]"
        assert parsed["reviewer"] == "writelab_adapter"


# ===========================================================================
# TestValidateRedaction — A18B L3
# ===========================================================================

class TestValidateRedaction:
    """paper validate should redact errors and reasons containing sensitive data."""

    def test_validate_errors_redacted(self, tmp_path):
        """Validation errors should be redacted via _redact_str."""
        state = {
            "task_id": "TASK-VR1", "status": "completed",
            "acceptance_result": {"status": "bad", "reasons": []},
        }
        _make_run_dir(tmp_path, "paper-vr1", state)
        errors = ["missing field: paragraph_text: raw secret value in output"]
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-vr1"), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=errors):
            result = _invoke(["paper", "validate", "--run-id", "paper-vr1"])
        assert result.exit_code == 1
        assert "raw secret value in output" not in result.output
        assert "[REDACTED]" in result.output

    def test_validate_reasons_redacted(self, tmp_path):
        """Acceptance reasons should be redacted via _redact_str."""
        state = {
            "task_id": "TASK-VR2", "status": "completed",
            "acceptance_result": {
                "status": "accepted",
                "reasons": ["writelab_token: secret-token-xyz exposed in log"],
            },
        }
        _make_run_dir(tmp_path, "paper-vr2", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-vr2"), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=[]):
            result = _invoke(["paper", "validate", "--run-id", "paper-vr2"])
        assert result.exit_code == 0
        assert "secret-token-xyz" not in result.output

    def test_validate_json_redacts_errors(self, tmp_path):
        """--json validation_errors should be deep-redacted."""
        state = {
            "task_id": "TASK-VR3", "status": "completed",
            "acceptance_result": {"status": "bad", "reasons": []},
        }
        _make_run_dir(tmp_path, "paper-vr3", state)
        errors = [
            {"paragraph_text": "secret leaked here", "message": "field validation failed"},
        ]
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-vr3"), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=errors):
            result = _invoke(["paper", "validate", "--run-id", "paper-vr3", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["validation_errors"][0]["paragraph_text"] == "[REDACTED]"
        assert parsed["validation_errors"][0]["message"] == "field validation failed"
