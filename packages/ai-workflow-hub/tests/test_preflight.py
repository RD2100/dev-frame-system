from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_workflow_hub.preflight import run_apply_preflight


def _marker_path(project_path: Path) -> Path:
    return project_path / ".aiworkflow" / "session" / "current.json"


def _write_marker(project_path: Path, data: object) -> None:
    marker = _marker_path(project_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(data), encoding="utf-8")


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


@pytest.fixture(autouse=True)
def safe_preflight_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    import ai_workflow_hub.config_loader as config_loader
    import ai_workflow_hub.git_utils as git_utils
    import ai_workflow_hub.opencode_client as opencode_client

    monkeypatch.setattr(opencode_client, "opencode_is_available", lambda: True)
    monkeypatch.setattr(git_utils, "is_worktree_clean", lambda _path: True)
    monkeypatch.setattr(git_utils, "is_main_branch", lambda _path: False)
    monkeypatch.setattr(
        config_loader,
        "get_execution_policy",
        lambda: {
            "release_policy": {
                "allow_push": False,
                "allow_pr_create": False,
                "allow_merge": False,
                "allow_deploy": False,
                "allow_ci_fix": False,
            }
        },
    )


@pytest.mark.parametrize("marker", [None, "{broken", {"status": "pending"}])
def test_incomplete_session_marker_blocks_apply(tmp_path: Path, marker: object) -> None:
    if isinstance(marker, str):
        path = _marker_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text(marker, encoding="utf-8")
    elif marker is not None:
        _write_marker(tmp_path, marker)

    result = run_apply_preflight("project", project_path=str(tmp_path))

    assert result["allowed"] is False
    assert result["result"] == "BLOCKED"
    assert next(c for c in result["checks"] if c["name"] == "session_gate")["status"] == "BLOCKED"


def test_stale_session_marker_blocks_apply(tmp_path: Path) -> None:
    marker = _valid_marker(tmp_path)
    marker["project_path"] = str(tmp_path / "other")
    _write_marker(tmp_path, marker)

    result = run_apply_preflight("project", project_path=str(tmp_path))

    assert result["allowed"] is False
    assert result["result"] == "BLOCKED"


def test_complete_marker_allows_apply_and_policy_warn_stays_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai_workflow_hub.config_loader as config_loader

    _write_marker(tmp_path, _valid_marker(tmp_path))
    monkeypatch.setattr(
        config_loader,
        "get_execution_policy",
        lambda: {"release_policy": {"allow_ci_fix": True}},
    )

    result = run_apply_preflight("project", project_path=str(tmp_path))

    assert result["allowed"] is True
    assert result["result"] == "WARN"
    assert next(c for c in result["checks"] if c["name"] == "session_gate")["status"] == "PASS"
