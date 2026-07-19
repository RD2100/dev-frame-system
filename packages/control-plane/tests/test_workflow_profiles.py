"""Production-path contracts for deterministic, planned-only workflow profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError
from jsonschema.validators import validator_for

from control_plane.custom_skills import save_at as save_skills_at
from control_plane.go_dispatch import load_go_run_result, run_go_dispatch
from control_plane.methodology_dispatch import (
    resolve_methodology,
    resolve_workflow_profile,
)
from control_plane.rules_config import save_at as save_rules_at
from control_plane.run_index import build_run_index
from control_plane.scope_resolver import Scope
from control_plane.skill_usage_validator import validate_skill_usage
from control_plane.stage_executor import execute_load_input


REPO_ROOT = Path(__file__).resolve().parents[3]


def _task_spec_schema() -> dict:
    return json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "task-spec.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )


def _validate_task_spec(task_spec: dict) -> None:
    schema = _task_spec_schema()
    validator_for(schema)(schema).validate(task_spec)


def test_coding_profile_is_deterministic_and_planned_only() -> None:
    first = resolve_workflow_profile("coding")
    second = resolve_workflow_profile("coding")

    assert first == second
    assert first["profile_id"] == "governed-coding-v1"
    assert first["selection_source"] == "coding_workflow_entrypoint"
    assert first["resolution_status"] == "selected"
    assert first["execution_state"] == "planned_only"
    assert [stage["stage_id"] for stage in first["ordered_stages"]] == [
        "intent",
        "implementation",
        "evidence",
        "review",
    ]
    assert all(not stage["permissions"]["network"] for stage in first["ordered_stages"])
    assert all(not stage["permissions"]["credentials"] for stage in first["ordered_stages"])
    assert first["profile_fingerprint"].startswith("sha256:")


def test_generic_context_fails_closed_without_keyword_inference() -> None:
    for value in (None, "generic", "paper mentioned in free text", "code search"):
        profile = resolve_workflow_profile(value)
        assert profile["profile_id"] == "unresolved"
        assert profile["resolution_status"] == "human_required"
        assert profile["execution_state"] == "planned_only"
        assert profile["ordered_stages"] == []
        assert profile["constraints"]["read_only"] is True
        assert profile["constraints"]["network_enabled"] is False


def test_generic_fail_closed_profile_is_recordable_in_task_spec() -> None:
    profile = resolve_workflow_profile("paper mentioned in free text")
    task_spec = {
        "task_id": "generic-task",
        "title": "Ambiguous task",
        "priority": "P2",
        "status": "pending_human_decision",
        "description": "Await a trusted structured work type.",
        "work_type": "generic",
        "workflow_profile": profile,
    }

    _validate_task_spec(task_spec)


def test_task_spec_rejects_mismatched_or_partial_profile_contract() -> None:
    profile = resolve_workflow_profile("paper")
    base = {
        "task_id": "mismatched-task",
        "title": "Mismatched task",
        "priority": "P2",
        "status": "ready",
        "description": "Reject contradictory structured workflow context.",
    }

    with pytest.raises(ValidationError):
        _validate_task_spec({**base, "work_type": "coding", "workflow_profile": profile})
    with pytest.raises(ValidationError):
        _validate_task_spec({**base, "work_type": "paper"})
    with pytest.raises(ValidationError):
        _validate_task_spec({**base, "workflow_profile": profile})


def test_paper_profile_records_external_gates_without_adopting_dirty_skills() -> None:
    profile = resolve_workflow_profile("paper")
    stages = {stage["skill_id"]: stage for stage in profile["ordered_stages"]}

    assert profile["profile_id"] == "governed-paper-v1"
    assert profile["execution_state"] == "planned_only"
    assert profile["human_gate_required"] is True
    for skill_id in ("agent-reach", "humanize", "ai-check"):
        assert stages[skill_id]["availability"] == "not_adopted"
        assert stages[skill_id]["skill_fingerprint"] is None
        assert stages[skill_id]["human_gate"] == "required_before_execution"
    assert "citations_numbers_formulas_names_claims_unchanged" in stages[
        "humanize"
    ]["required_evidence"]
    assert "diagnostic_only_no_authorship_claim" in stages["ai-check"][
        "required_evidence"
    ]


def test_project_and_p0_constraints_only_tighten_profile_permissions(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    save_skills_at(
        runtime,
        Scope.GLOBAL,
        None,
        [{"id": "read-only", "title": "Read only", "readOnly": True}],
    )
    save_rules_at(
        runtime,
        Scope.PROJECT,
        "demo",
        [{"id": "no-network", "priority": "P0", "rule": "no-network"}],
    )

    coding = resolve_workflow_profile(
        "coding", runtime_dir=runtime, project_id="demo"
    )
    paper = resolve_workflow_profile(
        "paper", runtime_dir=runtime, project_id="demo"
    )

    assert coding["constraints"]["read_only"] is True
    assert all(not stage["permissions"]["write"] for stage in coding["ordered_stages"])
    assert paper["constraints"]["network_enabled"] is False
    assert all(not stage["permissions"]["network"] for stage in paper["ordered_stages"])


def test_plain_coding_dispatch_records_profile_in_task_and_run_projection(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project"
    project.mkdir()
    runtime = tmp_path / "runtime"

    result = run_go_dispatch(
        project,
        "Implement the bounded feature.",
        runtime_dir=runtime,
        agents=1,
        execute=False,
    )

    assert result.methodology is None
    assert result.workflow_profile is not None
    assert result.workflow_profile["profile_id"] == "governed-coding-v1"
    task_spec = json.loads(
        Path(result.agents[0].task_spec_path).read_text(encoding="utf-8")
    )
    _validate_task_spec(task_spec)
    assert task_spec["work_type"] == "coding"
    assert task_spec["workflow_profile"] == result.workflow_profile
    assert "skill_usage" not in task_spec

    loaded = load_go_run_result(runtime, result.go_run_id)
    assert loaded.workflow_profile == result.workflow_profile
    raw_go = next(
        entry
        for entry in build_run_index(runtime)["runs"]
        if entry["adapter_id"] == "go_run"
    )
    domain_refs = raw_go["record"]["domain_refs"]
    assert domain_refs["workflow_profile_id"] == "governed-coding-v1"
    assert domain_refs["workflow_profile_fingerprint"] == result.workflow_profile[
        "profile_fingerprint"
    ]
    assert raw_go["record"]["acceptance_state"] != "final_ready"


def test_explicit_methodology_trigger_remains_compatible_with_automatic_profile(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project"
    project.mkdir()

    result = run_go_dispatch(
        project,
        "@tdd Add the bounded feature.",
        runtime_dir=tmp_path / "runtime",
        agents=1,
        execute=False,
    )

    assert result.methodology is not None
    assert result.methodology["skill_id"] == "tdd"
    assert result.workflow_profile is not None
    assert result.workflow_profile["profile_id"] == "governed-coding-v1"
    assert result.requirement == "Add the bounded feature."


def test_paper_production_stage_records_plan_without_usage_or_acceptance(
    tmp_path: Path,
) -> None:
    paper_project = tmp_path / "paper-project"

    result = execute_load_input(paper_project)

    assert result.status == "completed"
    task_spec = json.loads(
        (paper_project / "TASKSPEC.json").read_text(encoding="utf-8")
    )
    _validate_task_spec(task_spec)
    assert task_spec["work_type"] == "paper"
    assert task_spec["workflow_profile"]["profile_id"] == "governed-paper-v1"
    assert task_spec["workflow_profile"]["execution_state"] == "planned_only"
    assert "skill_usage" not in task_spec
    assert not (paper_project / "closure" / "FINAL_VERDICT.json").exists()
    assert validate_skill_usage({"skill_usage": []}).valid


def test_legacy_task_spec_and_methodology_contract_remain_valid() -> None:
    legacy = {
        "task_id": "legacy-task",
        "title": "Legacy task",
        "priority": "P2",
        "status": "ready",
        "description": "A legacy TaskSpec without workflow profile fields.",
    }
    _validate_task_spec(legacy)
    effective, methodology = resolve_methodology("Add a plain feature.")
    assert effective == "Add a plain feature."
    assert methodology is None


def test_task_spec_schema_mirror_has_the_same_contract() -> None:
    canonical = _task_spec_schema()
    mirror = json.loads(
        (
            REPO_ROOT
            / "packages"
            / "test-frame"
            / "schemas"
            / "agent-runtime"
            / "task-spec.schema.json"
        ).read_text(encoding="utf-8-sig")
    )
    assert mirror == canonical
