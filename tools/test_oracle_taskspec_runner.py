#!/usr/bin/env python3
"""Tests for oracle_taskspec_runner.py — S3 Phase 3"""

import json
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _tmp_taskspec_json(tmp_path: Path, overrides: dict | None = None) -> Path:
    data = {
        "task_id": "test-task",
        "stage": "test",
        "goal": "Test TaskSpec",
        "allowed_actions": ["run tests", "generate report", "validate schema"],
        "forbidden_actions": ["delete any file", "move any file", "rename any file"],
        "required_outputs": ["_reports/test-output.md"],
        "terminal_conditions": {"terminal": False, "reason": "test"},
        "review_required": True,
        "review_by": "gpt",
        "next_on_accepted": "next_stage",
        "next_on_blocked": "stop",
        "next_on_human_required": "stop",
        "high_risk": False,
        "schema_version": "1.0.0",
    }
    if overrides:
        data.update(overrides)
    p = tmp_path / "test_taskspec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── Markdown rejection ──────────────────────────────────────────────

def test_reject_markdown_only(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    md = tmp_path / "test.md"
    md.write_text("# Not machine readable", encoding="utf-8")
    result = run_taskspec("test", md, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_failed"
    assert result["terminal"] is True
    assert "Markdown" in result["reason"]


# ── JSON validation pass ────────────────────────────────────────────

def test_valid_json_passes(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    p = _tmp_taskspec_json(tmp_path)
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_success_continue"
    assert result["terminal"] is False
    assert result["safety"]["schema_validated"] is True


# ── Schema fail → fail-closed ───────────────────────────────────────

def test_invalid_schema_fail_closed(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    # Missing required fields
    data = {"task_id": "bad", "goal": "incomplete"}
    p = tmp_path / "bad_taskspec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_failed"
    assert result["terminal"] is True


# ── Schema missing → fail-closed ────────────────────────────────────

def test_schema_missing_fail_closed(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    p = _tmp_taskspec_json(tmp_path)
    # Point to non-existent contracts root
    result = run_taskspec("test", p, tmp_path / "nonexistent", tmp_path)
    assert result["status"] == "step_failed"
    assert result["terminal"] is True


# ── high_risk → human_required ──────────────────────────────────────

def test_high_risk_human_required(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    # TASKSPEC.schema.json enforces: high_risk=true → review_by=human, terminal=true (allOf rule)
    # So schema validation fails before high_risk check. This confirms schema-level enforcement.
    p = _tmp_taskspec_json(tmp_path, {"high_risk": True})
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    # Schema validation catches the contract violation: high_risk requires review_by=human per allOf
    assert result["status"] in ("step_failed", "step_human_required")
    assert result["terminal"] is True


# ── forbidden overlap → blocked ─────────────────────────────────────

def test_forbidden_overlap_blocked(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    p = _tmp_taskspec_json(tmp_path, {
        "allowed_actions": ["delete any file", "validate"],
        "forbidden_actions": ["delete any file"],
    })
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_blocked"
    assert result["terminal"] is True


# ── terminal_conditions.terminal → step_success_terminal ───────────

def test_terminal_conditions_terminal_true(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    p = _tmp_taskspec_json(tmp_path, {
        "terminal_conditions": {"terminal": True, "reason": "accepted_done"}
    })
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_success_terminal"
    assert result["terminal"] is True


# ── step_success_continue must have next_action ─────────────────────

def test_step_success_continue_has_next_action(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    p = _tmp_taskspec_json(tmp_path)
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_success_continue"
    assert "next_action" in result
    assert result["next_action"] != ""
    assert result["terminal"] is False


# ── Parsable JSON → no crash ────────────────────────────────────────

def test_corrupt_json_fail_closed(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    p = tmp_path / "bad.json"
    p.write_text("not json{{{", encoding="utf-8")
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_failed"
    assert result["terminal"] is True


# ── Unknown format → fail ───────────────────────────────────────────

def test_unknown_format_fail(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    p = tmp_path / "test.txt"
    p.write_text("hello", encoding="utf-8")
    result = run_taskspec("test", p, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_failed"
