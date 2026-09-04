"""Tests for the root PLAN.md single-authority gate."""
from __future__ import annotations

from pathlib import Path

from control_plane.docs_drift_validator import (
    REQUIRED_PLAN_HEADINGS,
    build_docs_drift_payload,
    derive_docs_drift,
    validate_docs_drift,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def _plan_text() -> str:
    headings = "\n\n".join(
        f"## {heading}\n\ncontent" for heading in REQUIRED_PLAN_HEADINGS
    )
    return f"# Plan\n\nCurrent verdict: **candidate**\n\n{headings}\n"


def _payload(**overrides: object) -> dict:
    plan_text = _plan_text()
    payload = {
        "plan_exists": True,
        "plan_text": plan_text,
        "plan_size": len(plan_text.encode("utf-8")),
        "plan_read_error": None,
        "agents_exists": True,
        "agents_text": "PLAN.md is the only human development authority.",
        "agents_read_error": None,
        "docs_files": [],
        "legacy_root_files": [],
    }
    payload.update(overrides)
    return payload


def test_valid_single_plan_payload_passes() -> None:
    result = validate_docs_drift(_payload())
    assert result.valid, result.errors


def test_missing_plan_fails() -> None:
    result = validate_docs_drift(
        _payload(plan_exists=False, plan_text="", plan_size=0)
    )
    assert not result.valid
    assert any("PLAN.md is missing" in error for error in result.errors)


def test_duplicate_verdict_and_missing_heading_fail() -> None:
    text = _plan_text().replace("## Human Gates\n\ncontent", "")
    text += "\nCurrent verdict: **duplicate**\n"
    result = validate_docs_drift(_payload(plan_text=text))
    assert not result.valid
    assert any("Current verdict" in error for error in result.errors)
    assert any("Human Gates" in error for error in result.errors)


def test_retired_docs_tree_and_root_docs_fail() -> None:
    result = validate_docs_drift(
        _payload(
            docs_files=["docs/status/old-plan.md"],
            legacy_root_files=["README.md", "AGENT_HANDOFF.md"],
        )
    )
    assert not result.valid
    assert any("docs/status/old-plan.md" in error for error in result.errors)
    assert any("README.md" in error for error in result.errors)


def test_agents_entrypoint_must_declare_authority() -> None:
    result = validate_docs_drift(_payload(agents_text="Read PLAN.md."))
    assert not result.valid
    assert any("only human development authority" in error for error in result.errors)


def test_projection_uses_same_fail_closed_checks_without_mutation() -> None:
    payload = _payload(docs_files=["docs/legacy.md"])
    original = list(payload["docs_files"])
    projection = derive_docs_drift(payload)
    assert not projection["valid"]
    assert projection["docs_file_count"] == 1
    assert projection["current_verdict_count"] == 1
    assert payload["docs_files"] == original


def test_current_repository_has_one_complete_plan_and_no_retired_docs() -> None:
    payload = build_docs_drift_payload(REPO_ROOT)
    result = validate_docs_drift(payload)
    assert result.valid, "\n".join(result.errors)
    projection = derive_docs_drift(payload)
    assert projection["current_verdict_count"] == 1
    assert projection["heading_counts"]["Next Action"] == 1
    assert projection["docs_file_count"] == 0
    assert projection["legacy_root_file_count"] == 0
