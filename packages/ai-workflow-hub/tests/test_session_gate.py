from __future__ import annotations

import json
from pathlib import Path

from ai_workflow_hub.session_gate import (
    REQUIRED_FACTS,
    ensure_session_marker,
    initialize_session_marker,
    validate_session_marker,
)


def _marker_path(project_path: Path) -> Path:
    return project_path / ".aiworkflow" / "session" / "current.json"


def _write_marker(project_path: Path, data: object) -> Path:
    marker = _marker_path(project_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(data), encoding="utf-8")
    return marker


def _valid_marker(project_path: Path) -> dict[str, object]:
    return {
        "status": "ready_for_file_edits",
        "startup_gate": {
            "active_memory_loaded": True,
            "project_conventions_loaded": True,
            "required_skills_loaded": True,
            "slice_plan_created": True,
        },
        "project_path": str(project_path.resolve()),
    }


def test_initialize_is_pending_and_repeated_validation_stays_incomplete(tmp_path: Path) -> None:
    initialize_session_marker(str(tmp_path))
    before = _marker_path(tmp_path).read_bytes()

    first = validate_session_marker(str(tmp_path))
    second = validate_session_marker(str(tmp_path))

    assert first["complete"] is False
    assert second["complete"] is False
    assert "startup_gate.slice_plan_created" in second["missing_fields"]
    assert _marker_path(tmp_path).read_bytes() == before


def test_validator_rejects_truthy_non_boolean_and_stale_project(tmp_path: Path) -> None:
    marker = _valid_marker(tmp_path)
    marker["startup_gate"]["active_memory_loaded"] = "true"  # type: ignore[index]
    marker["project_path"] = str(tmp_path / "other")
    _write_marker(tmp_path, marker)

    result = validate_session_marker(str(tmp_path))

    assert result["complete"] is False
    assert result["stale"] is True
    assert "startup_gate.active_memory_loaded" in result["missing_fields"]


def test_validator_preserves_malformed_marker(tmp_path: Path) -> None:
    marker = _marker_path(tmp_path)
    marker.parent.mkdir(parents=True)
    marker.write_text("{broken", encoding="utf-8")

    result = ensure_session_marker(str(tmp_path))

    assert result["complete"] is False
    assert result["malformed"] is True
    assert marker.read_text(encoding="utf-8") == "{broken"


def test_complete_marker_passes_without_legacy_blackboard_facts(tmp_path: Path) -> None:
    _write_marker(tmp_path, _valid_marker(tmp_path))

    result = validate_session_marker(str(tmp_path))

    assert result["complete"] is True
    assert result["missing_fields"] == []
    assert "startup_gate.bb_register" not in REQUIRED_FACTS
    assert REQUIRED_FACTS["startup_gate.slice_plan_created"] is True
