"""test_paper_a19_safe_e2e.py — A19 PAPER-REALISTIC-SAFE-E2E Tests.

Proves the full paper CLI lifecycle using synthetic-but-realistic fixtures:
  paper go (human_required) → paper resume → paper ledger → paper evidence
  → paper validate → paper status → paper list

Privacy assertions at every step: no paragraph_text or writelab_token values
leak to CLI output.  state.json on disk is clean.

All runtime / ledger / gate APIs are mocked to avoid real invocations.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from ai_workflow_hub.cli import app, _redact_str, _deep_redact

runner = CliRunner()

_RT_PATH = "ai_workflow_hub.context_layer.adapters.paper_runtime"
_LEDGER_PATH = "ai_workflow_hub.context_layer.adapters.paper_issue_ledger"
_GATE_PATH = "ai_workflow_hub.context_layer.adapters.paper_acceptance_gate"

SENSITIVE_KEYS = ("paragraph_text", "writelab_token")
SENSITIVE_VALUES = (
    "This is a raw manuscript excerpt about quantum entanglement",
    "tok-secret-writelab-abc123",
    "paragraph_text: leaked manuscript content here",
    "writelab_token=hidden-api-key-xyz",
)


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


def _assert_privacy_clean(output: str, label: str = ""):
    """Assert no sensitive values leak in CLI output."""
    for val in SENSITIVE_VALUES:
        assert val not in output, (
            f"[{label}] Sensitive value leaked: '{val[:40]}...' in output"
        )
    # Check that sensitive keys followed by actual values don't appear
    # (the key name alone is OK, key + value is not)
    import re
    for key in SENSITIVE_KEYS:
        # key: <non-empty, non-REDACTED value>
        m = re.search(rf'{key}\s*[:=]\s*(?!\[REDACTED\])(\S+)', output, re.IGNORECASE)
        if m:
            assert False, (
                f"[{label}] Sensitive key '{key}' with unredacted value: {m.group(0)[:60]}"
            )


# ===========================================================================
# Synthetic Fixtures
# ===========================================================================

TASK_ID = "task-synth-a19-001"
PROJECT_ID = "proj-synth-a19"
RUN_ID = "paper-synth-a19"

SYNTHETIC_ISSUES = [
    {
        "issue_id": "synth-001",
        "issue_type": "structure",
        "severity": "critical",
        "blocking": True,
        "human_required": True,
        "evidence": "Section 3 lacks methodology description",
        "recommendation": "Add detailed methodology section",
        "description": "Missing methodology in results section",
    },
    {
        "issue_id": "synth-002",
        "issue_type": "citation",
        "severity": "major",
        "blocking": False,
        "human_required": False,
        "evidence": "Reference [12] is outdated (2019 version)",
        "recommendation": "Update to 2024 edition",
        "description": "Outdated citation in literature review",
    },
    {
        "issue_id": "synth-003",
        "issue_type": "expression",
        "severity": "minor",
        "blocking": False,
        "human_required": False,
        "evidence": "Ambiguous phrasing in abstract line 3",
        "recommendation": "Rewrite for clarity",
        "description": "Unclear expression in abstract",
    },
]

SYNTHETIC_ACCEPTANCE = {
    "status": "human_required",
    "reasons": ["Blocking issue synth-001 requires human review"],
    "blocking_issues": [SYNTHETIC_ISSUES[0]],
    "non_blocking_issues": SYNTHETIC_ISSUES[1:],
    "reviewer": "writelab_adapter",
    "evidence_pack_ref": "ep-synth-a19-001",
    "privacy_attestation": {
        "no_full_text": True,
        "no_api_keys": True,
        "privacy_ok": True,
    },
}

SYNTHETIC_MANIFEST = {
    "reviewer": "writelab_adapter",
    "manifest_status": "complete",
    "evidence_pack_ref": "ep-synth-a19-001",
    "privacy_attestation": {"privacy_ok": True},
    "entries": [
        {"source": "expression_check", "evidence_type": "expression",
         "status": "complete", "issue_count": 1},
        {"source": "structure_check", "evidence_type": "structure",
         "status": "complete", "issue_count": 1},
        {"source": "citation_check", "evidence_type": "citation",
         "status": "complete", "issue_count": 1},
    ],
}

LEDGER_SUMMARY = {
    "task_id": TASK_ID, "total": 3, "open": 1, "resolved": 2,
    "blocking": 0, "critical": 0,
}

RESOLVED_ISSUES = [
    {**SYNTHETIC_ISSUES[0], "status": "resolved"},
    {**SYNTHETIC_ISSUES[1], "status": "resolved"},
    {**SYNTHETIC_ISSUES[2], "status": "open"},
]


# ===========================================================================
# TestA19LifecycleChain — Full command chain E2E
# ===========================================================================

class TestA19LifecycleChain:
    """Prove full lifecycle: go → resume → ledger → evidence → validate → status → list."""

    def test_go_creates_run_human_required(self, tmp_path):
        """paper go should create run and pause at human gate."""
        mock_create = {
            "run_id": RUN_ID, "run_dir": str(tmp_path / RUN_ID),
            "task_id": TASK_ID, "project_id": PROJECT_ID, "status": "created",
        }
        mock_execute = {
            "run_id": RUN_ID, "status": "human_required",
            "state": {
                "task_id": TASK_ID, "executed_nodes": ["parser", "human_gate"],
                "acceptance_status": "human_required", "blocking_count": 1,
            },
            "gate_artifact": str(tmp_path / RUN_ID / "paper-human-gate.md"),
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create), \
             patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_execute), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "go", "--task", TASK_ID, "--project", PROJECT_ID])

        assert result.exit_code == 0
        assert "human_required" in result.output
        assert RUN_ID in result.output
        _assert_privacy_clean(result.output, "go")

    def test_resume_approved(self, tmp_path):
        """paper resume with approved decision should complete the run."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "executed_nodes": ["parser", "human_gate", "finalizer"],
            "acceptance_status": "accepted_with_limitation",
            "acceptance_result": {**SYNTHETIC_ACCEPTANCE, "status": "accepted_with_limitation"},
            "evidence_manifest": SYNTHETIC_MANIFEST,
            "blocking_count": 0,
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        mock_resume = {
            "run_id": RUN_ID, "status": "completed",
            "state": state,
            "warnings": [],
        }
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.resume_paper_run", return_value=mock_resume), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "resume", "--run-id", RUN_ID,
                              "--decision", "approved", "--reviewer", "dr-smith"])

        assert result.exit_code == 0
        assert "completed" in result.output
        _assert_privacy_clean(result.output, "resume")

    def test_ledger_after_resume(self, tmp_path):
        """paper ledger should show resolved issues after resume."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "acceptance_result": {**SYNTHETIC_ACCEPTANCE, "status": "accepted_with_limitation"},
            "evidence_manifest": SYNTHETIC_MANIFEST,
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=LEDGER_SUMMARY), \
             patch(f"{_LEDGER_PATH}.get_open_issues",
                   return_value=[RESOLVED_ISSUES[2]]), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=True):
            result = _invoke(["paper", "ledger", "--run-id", RUN_ID])

        assert result.exit_code == 0
        assert TASK_ID in result.output
        assert "CLEAR" in result.output
        _assert_privacy_clean(result.output, "ledger")

    def test_evidence_after_resume(self, tmp_path):
        """paper evidence should show manifest entries."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "evidence_manifest": SYNTHETIC_MANIFEST,
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID):
            result = _invoke(["paper", "evidence", "--run-id", RUN_ID])

        assert result.exit_code == 0
        assert "writelab_adapter" in result.output
        assert "complete" in result.output
        _assert_privacy_clean(result.output, "evidence")

    def test_validate_after_resume(self, tmp_path):
        """paper validate should PASS on well-formed acceptance result."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "acceptance_result": {**SYNTHETIC_ACCEPTANCE, "status": "accepted_with_limitation"},
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=[]):
            result = _invoke(["paper", "validate", "--run-id", RUN_ID])

        assert result.exit_code == 0
        assert "PASSED" in result.output
        _assert_privacy_clean(result.output, "validate")

    def test_status_after_lifecycle(self, tmp_path):
        """paper status should show completed after full lifecycle."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "acceptance_result": {**SYNTHETIC_ACCEPTANCE, "status": "accepted_with_limitation"},
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        mock_status = {
            "run_id": RUN_ID, "task_id": TASK_ID, "project_id": PROJECT_ID,
            "status": "completed", "acceptance_status": "accepted_with_limitation",
            "blocking_count": 0, "human_required": False,
            "human_gate_decision": "approved", "reviewer_id": "dr-smith",
            "decision_round": 1, "executed_nodes": ["parser", "human_gate", "finalizer"],
            "error_message": "",
            "created_at": "2026-06-12T10:00:00", "updated_at": "2026-06-12T10:05:00",
        }
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_status), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "status", "--run-id", RUN_ID])

        assert result.exit_code == 0
        assert "completed" in result.output
        _assert_privacy_clean(result.output, "status")

    def test_list_shows_run(self, tmp_path):
        """paper list should show the run in the table."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "acceptance_result": {"status": "accepted_with_limitation"},
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "list"])

        assert result.exit_code == 0
        assert RUN_ID in result.output
        _assert_privacy_clean(result.output, "list")


# ===========================================================================
# TestA19PrivacyGuardrails — Sensitive data never leaks
# ===========================================================================

class TestA19PrivacyGuardrails:
    """Assert privacy at every CLI output point with synthetic sensitive data."""

    def test_go_warnings_with_sensitive_data_are_redacted(self, tmp_path):
        """Warnings containing paragraph_text should be redacted in go output."""
        mock_create = {
            "run_id": RUN_ID, "run_dir": str(tmp_path / RUN_ID),
            "task_id": TASK_ID, "project_id": PROJECT_ID, "status": "created",
        }
        mock_execute = {
            "run_id": RUN_ID, "status": "completed",
            "state": {"task_id": TASK_ID, "executed_nodes": ["parser", "finalizer"],
                      "acceptance_status": "accepted", "blocking_count": 0},
            "warnings": [
                "paragraph_text: leaked manuscript content in node parser",
                "writelab_token: hidden-api-key-xyz found in config",
            ],
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create), \
             patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_execute), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "go", "--task", TASK_ID])

        assert result.exit_code == 0
        _assert_privacy_clean(result.output, "go-warnings")
        assert "[REDACTED]" in result.output

    def test_ledger_json_with_sensitive_issue_fields(self, tmp_path):
        """JSON ledger output should deep-redact sensitive keys in issues."""
        state = {"task_id": TASK_ID, "status": "completed"}
        _make_run_dir(tmp_path, RUN_ID, state)
        # Issues with sensitive keys embedded
        issues_with_secrets = [
            {
                "issue_id": "priv-001", "issue_type": "privacy",
                "severity": "critical", "status": "open",
                "paragraph_text": "raw manuscript excerpt about biology",
                "description": "Privacy concern in section 2",
            },
        ]
        mock_summary = {"task_id": TASK_ID, "total": 1, "open": 1, "resolved": 0,
                        "blocking": 0, "critical": 1}
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=mock_summary), \
             patch(f"{_LEDGER_PATH}.get_open_issues", return_value=issues_with_secrets), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=False):
            result = _invoke(["paper", "ledger", "--run-id", RUN_ID, "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["issues"][0]["paragraph_text"] == "[REDACTED]"
        assert "raw manuscript excerpt" not in result.output

    def test_evidence_json_with_sensitive_manifest_fields(self, tmp_path):
        """JSON evidence output should deep-redact sensitive keys in manifest."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "evidence_manifest": {
                "reviewer": "writelab_adapter",
                "manifest_status": "complete",
                "writelab_token": "secret-token-in-manifest",
                "entries": [
                    {"source": "check_1", "evidence_type": "expression",
                     "paragraph_text": "leaked paragraph in evidence"},
                ],
            },
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID):
            result = _invoke(["paper", "evidence", "--run-id", RUN_ID, "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["writelab_token"] == "[REDACTED]"
        assert parsed["entries"][0]["paragraph_text"] == "[REDACTED]"
        assert "secret-token-in-manifest" not in result.output
        assert "leaked paragraph in evidence" not in result.output

    def test_validate_reasons_with_sensitive_data(self, tmp_path):
        """Validate reasons containing sensitive patterns should be redacted."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "acceptance_result": {
                "status": "accepted",
                "reasons": [
                    "All clear — paragraph_text: no leakage detected",
                    "writelab_token: properly scoped",
                ],
            },
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=[]):
            result = _invoke(["paper", "validate", "--run-id", RUN_ID])

        assert result.exit_code == 0
        assert "no leakage detected" not in result.output
        assert "properly scoped" not in result.output

    def test_state_json_on_disk_is_clean(self, tmp_path):
        """state.json written to disk should not contain sensitive values."""
        clean_state = {
            "task_id": TASK_ID, "status": "completed",
            "acceptance_result": {**SYNTHETIC_ACCEPTANCE, "status": "accepted_with_limitation"},
            "evidence_manifest": SYNTHETIC_MANIFEST,
        }
        run_dir = _make_run_dir(tmp_path, RUN_ID, clean_state)
        state_file = run_dir / "state.json"
        state_text = state_file.read_text(encoding="utf-8")

        # No sensitive VALUES in state.json
        for val in SENSITIVE_VALUES:
            assert val not in state_text, f"Sensitive value in state.json: {val[:40]}"


# ===========================================================================
# TestA19JsonOutputPrivacy — --json mode privacy
# ===========================================================================

class TestA19JsonOutputPrivacy:
    """Verify all --json output modes produce valid JSON with no leaks."""

    def test_go_json_privacy(self):
        """paper go --json should produce clean JSON."""
        mock_create = {
            "run_id": RUN_ID, "run_dir": "/tmp/x",
            "task_id": TASK_ID, "project_id": PROJECT_ID, "status": "created",
        }
        mock_execute = {
            "run_id": RUN_ID, "status": "completed",
            "state": {"task_id": TASK_ID, "executed_nodes": [],
                      "acceptance_status": "accepted", "blocking_count": 0,
                      "paragraph_text": "should be redacted"},
            "warnings": ["paragraph_text: leaked in warning"],
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create), \
             patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_execute), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "go", "--task", TASK_ID, "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "completed"
        _assert_privacy_clean(result.output, "go-json")

    def test_status_json_privacy(self):
        """paper status --json should produce clean JSON."""
        mock_info = {
            "run_id": RUN_ID, "task_id": TASK_ID, "project_id": PROJECT_ID,
            "status": "completed", "acceptance_status": "accepted",
            "blocking_count": 0, "human_required": False,
            "human_gate_decision": "", "reviewer_id": "",
            "decision_round": 0, "executed_nodes": [],
            "error_message": "", "created_at": "", "updated_at": "",
        }
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_info), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "status", "--run-id", RUN_ID, "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "completed"
        _assert_privacy_clean(result.output, "status-json")

    def test_ledger_json_privacy(self, tmp_path):
        """paper ledger --json should produce clean JSON."""
        state = {"task_id": TASK_ID, "status": "completed"}
        _make_run_dir(tmp_path, RUN_ID, state)
        issues = [
            {"issue_id": "j-001", "issue_type": "citation", "severity": "minor",
             "status": "open", "writelab_token": "tok-in-issue",
             "description": "normal description"},
        ]
        summary = {"task_id": TASK_ID, "total": 1, "open": 1, "resolved": 0,
                   "blocking": 0, "critical": 0}
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=summary), \
             patch(f"{_LEDGER_PATH}.get_open_issues", return_value=issues), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=True):
            result = _invoke(["paper", "ledger", "--run-id", RUN_ID, "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["issues"][0]["writelab_token"] == "[REDACTED]"
        assert "tok-in-issue" not in result.output

    def test_validate_json_privacy(self, tmp_path):
        """paper validate --json should produce clean JSON."""
        state = {
            "task_id": TASK_ID, "status": "completed",
            "acceptance_result": {
                "status": "accepted", "reasons": ["ok"],
                "paragraph_text": "secret in acceptance",
            },
        }
        _make_run_dir(tmp_path, RUN_ID, state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=RUN_ID), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=[]):
            result = _invoke(["paper", "validate", "--run-id", RUN_ID, "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["valid"] is True
        _assert_privacy_clean(result.output, "validate-json")


# ===========================================================================
# TestA19RedactHelpers — Unit tests for privacy helpers
# ===========================================================================

class TestA19RedactHelpers:
    """Comprehensive tests for _redact_str and _deep_redact with realistic data."""

    def test_redact_str_multiline(self):
        """_redact_str should handle multiline input."""
        text = "Line1: ok\nparagraph_text: secret on line2\nLine3: ok"
        result = _redact_str(text)
        assert "secret on line2" not in result
        assert "Line1: ok" in result
        assert "Line3: ok" in result

    def test_deep_redact_nested_acceptance_result(self):
        """_deep_redact should handle realistic acceptance result structure."""
        acceptance = {
            "status": "accepted_with_limitation",
            "reasons": ["All good"],
            "blocking_issues": [],
            "non_blocking_issues": [
                {"issue_id": "nb-1", "paragraph_text": "raw text in issue"},
            ],
            "reviewer": "writelab_adapter",
        }
        result = _deep_redact(acceptance)
        assert result["non_blocking_issues"][0]["paragraph_text"] == "[REDACTED]"
        assert "raw text in issue" not in str(result)

    def test_deep_redact_evidence_manifest(self):
        """_deep_redact should handle realistic evidence manifest."""
        manifest = {
            "reviewer": "writelab_adapter",
            "manifest_status": "complete",
            "entries": [
                {"source": "check_1", "paragraph_text": "leaked", "status": "ok"},
                {"source": "check_2", "writelab_token": "tok", "status": "ok"},
            ],
        }
        result = _deep_redact(manifest)
        assert result["entries"][0]["paragraph_text"] == "[REDACTED]"
        assert result["entries"][1]["writelab_token"] == "[REDACTED]"
        assert result["reviewer"] == "writelab_adapter"

    def test_redact_str_json_in_error_message(self):
        """_redact_str should handle JSON-like error messages."""
        text = 'Validation error: {"paragraph_text": "secret value", "status": "ok"}'
        result = _redact_str(text)
        assert "secret value" not in result

    def test_deep_redact_empty_and_none(self):
        """_deep_redact should handle edge cases gracefully."""
        assert _deep_redact(None) is None
        assert _deep_redact(42) == 42
        assert _deep_redact(True) is True
        assert _deep_redact(3.14) == 3.14
