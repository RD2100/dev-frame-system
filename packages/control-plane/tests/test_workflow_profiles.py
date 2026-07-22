"""Production-path contracts for deterministic, planned-only workflow profiles."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError
from jsonschema.validators import validator_for

import control_plane.go_dispatch as go_dispatch_module
import control_plane.methodology_dispatch as methodology_dispatch_module
from control_plane.custom_skills import save_at as save_skills_at
from control_plane.go_dispatch import (
    execute_go_run,
    load_go_run_result,
    run_go_dispatch,
)
from control_plane.methodology_dispatch import (
    WorkflowCanaryError,
    resolve_methodology,
    resolve_workflow_profile,
)
from control_plane.project_contract import slugify_project_id
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


def _write_workflow_canary_policy(runtime: Path, project: Path) -> Path:
    project_id = slugify_project_id(project)
    save_skills_at(
        runtime,
        Scope.PROJECT,
        project_id,
        [
            {
                "id": "workflow-canary-read-only",
                "title": "Workflow canary read only",
                "readOnly": True,
                "networkEnabled": False,
                "requireRedGreenEvidence": True,
            }
        ],
    )
    return runtime / project_id / "skills.json"


def _real_worker_command(sentinel: Path) -> list[str]:
    worker_code = (
        "from pathlib import Path; import os; "
        f"Path({str(sentinel)!r}).write_text('worker-ran', encoding='utf-8'); "
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport\\n\\n"
        "- **Status**: pass\\n"
        "- **Review Status**: draft\\n"
        "- **Changed Files**:\\n"
        "- (none)\\n"
        "- **Evidence**: real worker boundary probe\\n', encoding='utf-8')"
    )
    return [sys.executable, "-c", worker_code]


def _project_tree_snapshot(project: Path) -> dict[str, tuple[str, bytes]]:
    snapshot: dict[str, tuple[str, bytes]] = {}
    for path in sorted(
        project.rglob("*"),
        key=lambda item: item.relative_to(project).as_posix(),
    ):
        relative_path = path.relative_to(project).as_posix()
        if path.is_symlink():
            snapshot[relative_path] = (
                "symlink",
                str(path.readlink()).encode("utf-8"),
            )
        elif path.is_dir():
            snapshot[relative_path] = ("directory", b"")
        elif path.is_file():
            snapshot[relative_path] = ("file", path.read_bytes())
        else:
            snapshot[relative_path] = ("other", b"")
    return snapshot


def _run_workflow_canary_or_reproduce_legacy_worker(
    project: Path,
    runtime: Path,
    sentinel: Path,
):
    """Keep the original production failure reproducible after the API lands."""
    kwargs = {
        "runtime_dir": runtime,
        "agents": 1,
        "execute": True,
    }
    if "workflow_canary" in inspect.signature(run_go_dispatch).parameters:
        kwargs["workflow_canary"] = True
    else:
        kwargs["worker_command"] = _real_worker_command(sentinel)
    return run_go_dispatch(project, "@go read inspect the bounded source.", **kwargs)


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


@pytest.mark.parametrize(
    "requirement",
    [
        "@go reader inspect the bounded source.",
        "@go readonly inspect the bounded source.",
        "@go read-only inspect the bounded source.",
        "@go read",
        "@go read   \t",
    ],
    ids=["reader", "readonly", "read-only", "bare", "whitespace-only"],
)
def test_workflow_canary_rejects_inexact_activation_before_runtime_side_effects(
    tmp_path: Path,
    requirement: str,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    before = _project_tree_snapshot(runtime)

    with pytest.raises(
        WorkflowCanaryError,
        match='requires devframe code "@go read <goal>"',
    ):
        run_go_dispatch(
            project,
            requirement,
            runtime_dir=runtime,
            agents=1,
            execute=True,
            workflow_canary=True,
        )

    assert _project_tree_snapshot(runtime) == before
    assert not (runtime / "go-runs").exists()
    assert not (runtime / "rdgoal-outbox").exists()
    assert not (runtime / "rdgoal-reports").exists()


def test_workflow_canary_bypasses_the_real_command_worker_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    sentinel = tmp_path / "worker-ran.txt"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)

    real_worker = go_dispatch_module.CommandWorker
    real_builder = go_dispatch_module.build_go_worker_command
    constructed: list[str] = []
    built: list[str] = []

    class TrackingCommandWorker:
        def __init__(self, *args, **kwargs):
            constructed.append("CommandWorker")
            self._delegate = real_worker(*args, **kwargs)

        def run_packet(self, *args, **kwargs):
            return self._delegate.run_packet(*args, **kwargs)

    def tracking_builder(*args, **kwargs):
        built.append("build_go_worker_command")
        return real_builder(*args, **kwargs)

    def reject_acp_session(*args, **kwargs):
        raise AssertionError("workflow canary entered the ACP session boundary")

    monkeypatch.setattr(go_dispatch_module, "CommandWorker", TrackingCommandWorker)
    monkeypatch.setattr(go_dispatch_module, "build_go_worker_command", tracking_builder)
    monkeypatch.setattr(go_dispatch_module, "_run_one_agent_acp", reject_acp_session)

    result = _run_workflow_canary_or_reproduce_legacy_worker(
        project,
        runtime,
        sentinel,
    )

    assert result.methodology["selected_trigger"] == "@go read"
    assert result.methodology["read_only"] is True
    assert not sentinel.exists()
    assert constructed == []
    assert built == []
    assert result.status == "passed"
    assert result.agents[0].worker_command == []
    assert result.agents[0].worker_status == "passed"
    assert result.workflow_canary["mode"] == "canary_only"
    assert result.workflow_canary["status"] == "passed"
    assert [
        (stage["phase"], stage["stage_id"], stage["status"])
        for stage in result.workflow_canary["stage_results"]
    ] == [
        ("pre", "intent", "passed"),
        ("post", "evidence", "passed"),
    ]

    task_spec = json.loads(
        Path(result.agents[0].task_spec_path).read_text(encoding="utf-8")
    )
    report = Path(result.agents[0].report_path)
    report_text = report.read_text(encoding="utf-8")
    summary_path = (
        runtime
        / "rdgoal-reports"
        / result.project_id
        / Path(result.agents[0].packet_dir).name
        / "execution-summary.json"
    )
    assert "skill_usage" not in task_spec
    assert "**Review Status**: draft" in report_text
    assert "**Changed Files**:\n- (none)" in report_text
    assert "FinalVerdict" not in report_text
    assert summary_path.is_file()
    assert not list(runtime.rglob("FINAL_VERDICT.json"))
    assert not list(runtime.rglob("review.yaml"))
    assert not list(runtime.rglob("review.md"))


@pytest.mark.parametrize("failure_kind", ["missing", "malformed", "io_error"])
def test_workflow_canary_policy_failures_are_closed_before_any_side_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    project = tmp_path / f"code-project-{failure_kind}"
    runtime = tmp_path / f"runtime-{failure_kind}"
    sentinel = tmp_path / f"worker-ran-{failure_kind}.txt"
    project.mkdir()
    policy_path = runtime / slugify_project_id(project) / "skills.json"

    if failure_kind == "malformed":
        policy_path.parent.mkdir(parents=True)
        policy_path.write_text("{not-json", encoding="utf-8")
    elif failure_kind == "io_error":
        _write_workflow_canary_policy(runtime, project)
        original_read_bytes = Path.read_bytes

        def fail_policy_read(path: Path) -> bytes:
            if path.resolve() == policy_path.resolve():
                raise OSError("simulated policy read failure")
            return original_read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", fail_policy_read)

    with pytest.raises(ValueError, match="workflow canary") as error:
        _run_workflow_canary_or_reproduce_legacy_worker(
            project,
            runtime,
            sentinel,
        )

    assert type(error.value).__name__ == "WorkflowCanaryError"
    assert not sentinel.exists()
    assert not (runtime / "rdgoal-outbox").exists()
    assert not (runtime / "go-runs").exists()
    assert not (runtime / "rdgoal-reports").exists()


def test_workflow_canary_prepare_persists_canonical_immutable_binding(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    policy_path = _write_workflow_canary_policy(runtime, project)

    result = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        execute=False,
        workflow_canary=True,
    )

    canary = result.workflow_canary
    assert canary["contract_version"] == "coding-workflow-canary.v1"
    assert canary["mode"] == "canary_only"
    assert canary["selection_source"] == "explicit_cli_opt_in"
    assert canary["status"] == "prepared"
    assert canary["stage_results"] == []
    assert canary["policy_binding"] == {
        "resolved_path": str(policy_path.resolve()),
        "sha256": f"sha256:{hashlib.sha256(policy_path.read_bytes()).hexdigest()}",
    }
    assert canary["profile_binding"] == {
        "profile_id": result.workflow_profile["profile_id"],
        "profile_fingerprint": result.workflow_profile["profile_fingerprint"],
    }
    assert [
        (stage["phase"], stage["stage_id"], stage["skill_id"])
        for stage in canary["stage_bindings"]
    ] == [
        ("pre", "intent", "intent-framing-gate"),
        ("post", "evidence", "evidence-driven-acceptance"),
    ]
    for stage in canary["stage_bindings"]:
        source = REPO_ROOT / stage["source_path"]
        assert stage["skill_fingerprint"] == (
            f"sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}"
        )
    canonical_binding = {
        key: canary[key]
        for key in (
            "contract_version",
            "mode",
            "selection_source",
            "policy_binding",
            "profile_binding",
            "stage_bindings",
        )
    }
    canonical_bytes = json.dumps(
        canonical_binding,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert canary["binding_fingerprint"] == (
        f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"
    )
    assert result.agents[0].worker_command == []
    assert not Path(result.agents[0].packet_dir, "ExecutionReport.md").exists()
    assert not (runtime / "rdgoal-reports").exists()


@pytest.mark.parametrize(
    "invalid_options",
    [
        {"agents": 2},
        {"targets": ["src/app.py"]},
        {"worker_command": [sys.executable, "-c", "print('worker')"]},
        {"worker": "custom-worker"},
        {"model": "provider/model"},
        {"model_provider": "local-ollama"},
        {"opencode_agent": "plan"},
        {"acp_command": ["opencode", "acp"]},
        {"driver": "acp", "acp_command": ["opencode", "acp"]},
        {"isolate": True},
        {"apply_rdinit": True},
    ],
)
def test_workflow_canary_rejects_non_canary_execution_options_before_packets(
    tmp_path: Path,
    invalid_options: dict,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    options = {
        "runtime_dir": runtime,
        "agents": 1,
        "execute": False,
        "workflow_canary": True,
        **invalid_options,
    }

    with pytest.raises(ValueError, match="workflow canary"):
        run_go_dispatch(
            project,
            "@go read inspect the bounded source.",
            **options,
        )

    assert not (runtime / "rdgoal-outbox").exists()
    assert not (runtime / "go-runs").exists()


def test_workflow_canary_resume_rejects_policy_byte_drift_without_mutation(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    policy_path = _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata_before = metadata_path.read_bytes()
    policy_path.write_bytes(policy_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="workflow canary"):
        execute_go_run(runtime, prepared.go_run_id)

    assert metadata_path.read_bytes() == metadata_before
    assert not Path(prepared.agents[0].packet_dir, "ExecutionReport.md").exists()
    assert not (runtime / "rdgoal-reports").exists()


@pytest.mark.parametrize("drift_kind", ["profile", "skill_source", "skill_bytes"])
def test_workflow_canary_resume_rejects_profile_and_skill_drift_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    project = tmp_path / f"code-project-{drift_kind}"
    runtime = tmp_path / f"runtime-{drift_kind}"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata_before = metadata_path.read_bytes()

    if drift_kind == "profile":
        monkeypatch.setitem(
            methodology_dispatch_module._WORKFLOW_PROFILE_DEFINITIONS["coding"],
            "profile_version",
            "1.0.1-drift",
        )
    elif drift_kind == "skill_source":
        monkeypatch.setitem(
            methodology_dispatch_module.METHODOLOGY_DISPATCH[
                "intent-framing-gate"
            ],
            "source_path",
            "tools/skills/tdd/SKILL.md",
        )
    else:
        intent_source = (
            REPO_ROOT / "tools" / "skills" / "intent-framing-gate" / "SKILL.md"
        ).resolve()
        original_read_bytes = Path.read_bytes

        def drift_skill_bytes(path: Path) -> bytes:
            raw = original_read_bytes(path)
            return raw + b"\n# drift" if path.resolve() == intent_source else raw

        monkeypatch.setattr(Path, "read_bytes", drift_skill_bytes)

    with pytest.raises(ValueError, match="workflow canary"):
        execute_go_run(runtime, prepared.go_run_id)

    assert metadata_path.read_bytes() == metadata_before
    assert not Path(prepared.agents[0].packet_dir, "ExecutionReport.md").exists()
    assert not (runtime / "rdgoal-reports").exists()


def test_workflow_canary_resume_rejects_authority_metadata_injection(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["workflow_canary"]["final_ready"] = True
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metadata_before = metadata_path.read_bytes()

    with pytest.raises(ValueError, match="workflow canary"):
        execute_go_run(runtime, prepared.go_run_id)

    assert metadata_path.read_bytes() == metadata_before
    assert not Path(prepared.agents[0].packet_dir, "ExecutionReport.md").exists()
    assert not (runtime / "rdgoal-reports").exists()


def _assert_workflow_canary_resume_is_side_effect_free(
    runtime: Path,
    prepared,
    metadata_path: Path,
    metadata_before: bytes,
) -> None:
    error = None
    resume_run_id = (
        prepared.go_run_id.swapcase()
        if sys.platform == "win32"
        else prepared.go_run_id
    )
    try:
        execute_go_run(runtime, resume_run_id)
    except ValueError as exc:
        error = exc

    assert metadata_path.read_bytes() == metadata_before
    assert not Path(prepared.agents[0].packet_dir, "ExecutionReport.md").exists()
    assert not (runtime / "rdgoal-reports").exists()
    assert error is not None
    assert type(error).__name__ == "WorkflowCanaryError"
    assert "workflow canary" in str(error)


@pytest.mark.parametrize(
    "authority_fields",
    [
        {"final_ready": True},
        {"root_accepted": True},
        {"FinalVerdict": {"final_state": "final_ready"}},
        {
            "final_ready": True,
            "root_accepted": True,
            "FinalVerdict": {"final_state": "final_ready"},
        },
    ],
    ids=["final-ready", "root-accepted", "final-verdict", "combined"],
)
def test_workflow_canary_resume_rejects_top_level_authority_fields(
    tmp_path: Path,
    authority_fields: dict,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(authority_fields)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metadata_before = metadata_path.read_bytes()

    _assert_workflow_canary_resume_is_side_effect_free(
        runtime,
        prepared,
        metadata_path,
        metadata_before,
    )


def test_workflow_canary_resume_rejects_forged_internal_validation_marker(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["_workflow_canary_envelope_validated"] = True
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metadata_before = metadata_path.read_bytes()

    _assert_workflow_canary_resume_is_side_effect_free(
        runtime,
        prepared,
        metadata_path,
        metadata_before,
    )


def test_workflow_canary_resume_rejects_deleted_marker(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.pop("workflow_canary")
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metadata_before = metadata_path.read_bytes()

    _assert_workflow_canary_resume_is_side_effect_free(
        runtime,
        prepared,
        metadata_path,
        metadata_before,
    )


def test_workflow_canary_resume_rejects_deleted_marker_with_injected_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    sentinel = tmp_path / "worker-ran.txt"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.pop("workflow_canary")
    metadata["agents"][0]["worker_command"] = _real_worker_command(sentinel)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metadata_before = metadata_path.read_bytes()
    command_entries: list[str] = []
    acp_entries: list[str] = []
    real_worker = go_dispatch_module.CommandWorker

    class TrackingCommandWorker:
        def __init__(self, *args, **kwargs):
            command_entries.append("CommandWorker")
            self._delegate = real_worker(*args, **kwargs)

        def run_packet(self, *args, **kwargs):
            return self._delegate.run_packet(*args, **kwargs)

    def tracking_acp(*args, **kwargs):
        acp_entries.append("ACP")
        raise AssertionError("workflow canary entered the ACP boundary")

    monkeypatch.setattr(go_dispatch_module, "CommandWorker", TrackingCommandWorker)
    monkeypatch.setattr(go_dispatch_module, "_run_one_agent_acp", tracking_acp)

    with pytest.raises(WorkflowCanaryError, match="workflow canary"):
        execute_go_run(runtime, prepared.go_run_id)

    summary_path = (
        runtime
        / "rdgoal-reports"
        / prepared.project_id
        / Path(prepared.agents[0].packet_dir).name
        / "execution-summary.json"
    )
    assert metadata_path.read_bytes() == metadata_before
    assert not sentinel.exists()
    assert command_entries == []
    assert acp_entries == []
    assert not Path(prepared.agents[0].packet_dir, "ExecutionReport.md").exists()
    assert not summary_path.exists()


@pytest.mark.parametrize(
    "drift_kind",
    [
        "profile-object",
        "profile-id",
        "methodology-object",
        "selected-trigger",
        "agents-object",
        "agent-count",
        "agent-object",
        "shard-index",
        "shard-count",
        "targets",
        "model-provider",
        "isolated",
    ],
)
def test_workflow_canary_resume_classification_uses_persisted_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    project = tmp_path / f"code-project-{drift_kind}"
    runtime = tmp_path / f"runtime-{drift_kind}"
    sentinel = tmp_path / f"worker-ran-{drift_kind}.txt"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    assert metadata_path.parent.name.startswith("go-_workflow-canary_-")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.pop("workflow_canary")
    agent = metadata["agents"][0]
    agent["worker_command"] = _real_worker_command(sentinel)

    if drift_kind == "profile-object":
        metadata["workflow_profile"] = []
    elif drift_kind == "profile-id":
        metadata["workflow_profile"]["profile_id"] = "drifted-profile"
    elif drift_kind == "methodology-object":
        metadata["methodology"] = []
    elif drift_kind == "selected-trigger":
        metadata["methodology"]["selected_trigger"] = "@go"
    elif drift_kind == "agents-object":
        metadata["agents"] = {}
    elif drift_kind == "agent-count":
        metadata["agents"].append(dict(agent))
    elif drift_kind == "agent-object":
        metadata["agents"][0] = "drifted-agent"
    elif drift_kind == "shard-index":
        agent["shard_index"] = 2
    elif drift_kind == "shard-count":
        agent["shard_count"] = 2
    elif drift_kind == "targets":
        agent["targets"] = ["README.md"]
    elif drift_kind == "model-provider":
        agent["model_provider"] = "untrusted-provider"
    else:
        agent["isolated"] = True

    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metadata_before = metadata_path.read_bytes()
    boundary_entries: list[str] = []

    def reject_boundary(name: str):
        def reject(*_args, **_kwargs):
            boundary_entries.append(name)
            raise AssertionError(f"entered {name} before canary rejection")

        return reject

    monkeypatch.setattr(
        go_dispatch_module,
        "_execute_parallel",
        reject_boundary("ordinary-worker-or-acp"),
    )
    monkeypatch.setattr(
        "control_plane.stage_executor.execute_coding_workflow_canary",
        reject_boundary("canary-stage-report"),
    )
    monkeypatch.setattr(
        "control_plane.dispatch_packet.DispatchPacketStore.ingest_report",
        reject_boundary("report-summary"),
    )

    error = None
    try:
        execute_go_run(runtime, prepared.go_run_id)
    except Exception as exc:  # noqa: BLE001 - assert the exact boundary error below
        error = exc

    summary_path = (
        runtime
        / "rdgoal-reports"
        / prepared.project_id
        / Path(prepared.agents[0].packet_dir).name
        / "execution-summary.json"
    )
    assert boundary_entries == []
    assert type(error) is WorkflowCanaryError
    assert metadata_path.read_bytes() == metadata_before
    assert not sentinel.exists()
    assert not Path(prepared.agents[0].packet_dir, "ExecutionReport.md").exists()
    assert not summary_path.exists()


@pytest.mark.parametrize("operation", ["copy", "move"])
@pytest.mark.parametrize("adjust_run_id", [False, True])
def test_workflow_canary_resume_rejects_marker_on_ordinary_metadata_path(
    tmp_path: Path,
    operation: str,
    adjust_run_id: bool,
) -> None:
    project = tmp_path / f"code-project-{operation}-{adjust_run_id}"
    runtime = tmp_path / f"runtime-{operation}-{adjust_run_id}"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    source_metadata = Path(prepared.metadata_path)
    ordinary_run_id = f"go-ordinary-{operation}-{adjust_run_id}"
    ordinary_run_dir = runtime / "go-runs" / ordinary_run_id
    if operation == "copy":
        shutil.copytree(source_metadata.parent, ordinary_run_dir)
    else:
        source_metadata.parent.rename(ordinary_run_dir)
    ordinary_metadata = ordinary_run_dir / "go-run.json"
    if adjust_run_id:
        payload = json.loads(ordinary_metadata.read_text(encoding="utf-8"))
        payload["go_run_id"] = ordinary_run_id
        ordinary_metadata.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    before = _project_tree_snapshot(runtime)
    error = None

    try:
        execute_go_run(runtime, ordinary_run_id)
    except ValueError as exc:
        error = exc

    assert _project_tree_snapshot(runtime) == before
    assert type(error) is WorkflowCanaryError
    assert "workflow canary" in str(error)


def test_workflow_canary_resume_rejects_persisted_run_id_path_mismatch(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project-id-mismatch"
    runtime = tmp_path / "runtime-id-mismatch"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["go_run_id"] = "go-mismatched-persisted-id"
    metadata_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    before = _project_tree_snapshot(runtime)
    error = None

    try:
        execute_go_run(runtime, prepared.go_run_id)
    except ValueError as exc:
        error = exc

    assert _project_tree_snapshot(runtime) == before
    assert type(error) is WorkflowCanaryError
    assert "workflow canary" in str(error)


def test_workflow_canary_resume_accepts_matching_reserved_metadata_path(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project-valid-resume"
    runtime = tmp_path / "runtime-valid-resume"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    resume_run_id = (
        prepared.go_run_id.swapcase()
        if sys.platform == "win32"
        else prepared.go_run_id
    )

    result = execute_go_run(runtime, resume_run_id)

    assert result.status == "passed"
    assert result.workflow_canary["status"] == "passed"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction regression")
def test_workflow_canary_resume_rejects_reserved_metadata_junction_escape(
    tmp_path: Path,
) -> None:
    project = tmp_path / "code-project-junction"
    runtime = tmp_path / "runtime-junction"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    run_dir = metadata_path.parent
    backing_dir = tmp_path / "outside-canary-run"
    run_dir.rename(backing_dir)
    created = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(run_dir), str(backing_dir)],
        capture_output=True,
        check=False,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"junction creation unavailable: {created.stderr.strip()}")

    try:
        before = _project_tree_snapshot(runtime)
        error = None
        try:
            execute_go_run(runtime, prepared.go_run_id)
        except ValueError as exc:
            error = exc

        assert _project_tree_snapshot(runtime) == before
        assert type(error) is WorkflowCanaryError
        assert "workflow canary" in str(error)
    finally:
        if run_dir.exists():
            os.rmdir(run_dir)


@pytest.mark.parametrize(
    "blocked_shape",
    ["dispatch-not-ready", "task-deferred", "hard-stop", "draft-only"],
)
def test_workflow_canary_resume_rejects_blocked_dispatch_before_stages(
    tmp_path: Path,
    blocked_shape: str,
) -> None:
    project = tmp_path / f"code-project-{blocked_shape}"
    runtime = tmp_path / f"runtime-{blocked_shape}"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata_before = metadata_path.read_bytes()
    packet_root = Path(prepared.agents[0].packet_dir)
    packet_path = packet_root / "packet.json"
    task_spec_path = packet_root / "TASKSPEC.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    task_spec = json.loads(task_spec_path.read_text(encoding="utf-8"))
    if blocked_shape == "dispatch-not-ready":
        packet["dispatch_ready"] = False
    elif blocked_shape == "task-deferred":
        packet["task_spec"]["status"] = "deferred"
        task_spec["status"] = "deferred"
    elif blocked_shape == "hard-stop":
        packet["decision_mode"] = "hard_stop"
    else:
        packet["decision_mode"] = "draft_only"
    packet_path.write_text(
        json.dumps(packet, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    task_spec_path.write_text(
        json.dumps(task_spec, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    with pytest.raises(WorkflowCanaryError, match="workflow canary.*dispatch"):
        execute_go_run(runtime, prepared.go_run_id)

    summary_path = (
        runtime
        / "rdgoal-reports"
        / prepared.project_id
        / packet_root.name
        / "execution-summary.json"
    )
    assert metadata_path.read_bytes() == metadata_before
    assert not (packet_root / "ExecutionReport.md").exists()
    assert not summary_path.exists()


def test_workflow_canary_project_tree_delta_matches_reported_changed_files(
    tmp_path: Path,
) -> None:
    project = tmp_path / "fresh-code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / ".gitignore").write_text(
        "rules/project-contracts/\n",
        encoding="utf-8",
    )
    _write_workflow_canary_policy(runtime, project)
    before = _project_tree_snapshot(project)

    result = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        execute=True,
        workflow_canary=True,
    )

    after = _project_tree_snapshot(project)
    independent_delta = sorted(
        path
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    )
    summary_path = (
        runtime
        / "rdgoal-reports"
        / result.project_id
        / Path(result.agents[0].packet_dir).name
        / "execution-summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert result.status == "passed"
    assert before == after
    assert result.agents[0].changed_files == independent_delta
    assert summary["changed_files"] == independent_delta


def test_workflow_canary_rejects_runtime_inside_project_without_tree_mutation(
    tmp_path: Path,
) -> None:
    project = tmp_path / "fresh-code-project"
    runtime = project / ".devframe-runtime"
    project.mkdir()
    (project / "source.txt").write_bytes(b"original\x00bytes")
    _write_workflow_canary_policy(runtime, project)
    before = _project_tree_snapshot(project)

    with pytest.raises(
        WorkflowCanaryError,
        match="runtime directory must stay outside the project",
    ):
        run_go_dispatch(
            project,
            "@go read inspect the bounded source.",
            runtime_dir=runtime,
            agents=1,
            execute=True,
            workflow_canary=True,
        )

    assert _project_tree_snapshot(project) == before


@pytest.mark.parametrize(
    "downgraded_marker",
    [None, False, {}],
    ids=["null", "false", "empty-object"],
)
def test_workflow_canary_resume_rejects_downgraded_marker(
    tmp_path: Path,
    downgraded_marker: object,
) -> None:
    project = tmp_path / "code-project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    _write_workflow_canary_policy(runtime, project)
    prepared = run_go_dispatch(
        project,
        "@go read inspect the bounded source.",
        runtime_dir=runtime,
        agents=1,
        workflow_canary=True,
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["workflow_canary"] = downgraded_marker
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    metadata_before = metadata_path.read_bytes()

    _assert_workflow_canary_resume_is_side_effect_free(
        runtime,
        prepared,
        metadata_path,
        metadata_before,
    )


def test_plain_dispatch_keeps_workflow_canary_default_off(tmp_path: Path) -> None:
    project = tmp_path / "_workflow_canary_"
    project.mkdir()
    result = run_go_dispatch(
        project,
        "@go read inspect the ordinary bounded source.",
        runtime_dir=tmp_path / "runtime",
        agents=1,
    )

    metadata = json.loads(Path(result.metadata_path).read_text(encoding="utf-8"))
    loaded = load_go_run_result(tmp_path / "runtime", result.go_run_id)
    parameter = inspect.signature(run_go_dispatch).parameters["workflow_canary"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is False
    assert result.workflow_canary is None
    assert loaded.workflow_canary is None
    assert "workflow_canary" not in metadata
    assert metadata["go_run_id"] == Path(result.metadata_path).parent.name
    assert not Path(result.metadata_path).parent.name.startswith(
        "go-_workflow-canary_-"
    )
    assert result.agents[0].worker_command
