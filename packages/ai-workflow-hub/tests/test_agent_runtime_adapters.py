"""TDD tests for canonical TaskSpec / ExecutionReport adapters.

These tests drive the RED -> GREEN cycle for aligning
``task_spec_adapter`` and ``execution_report_adapter`` with the
canonical closed schemas in ``schemas/agent-runtime/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from ai_workflow_hub.executor_contract import (
    ExecutorContractValidationError,
    validate_executor_runtime,
)
from ai_workflow_hub.task_spec_adapter import (
    TaskSpecValidationError,
    from_task_spec,
)
from ai_workflow_hub.execution_report_adapter import (
    ExecutionReportError,
    to_execution_report,
)
from ai_workflow_hub.agent_runtime_schemas import (
    AgentRuntimeSchemaError,
    load_offline_validator,
)

# ------------------------------------------------------------------ #
# Canonical schema loading (from repo, never weakened)
# ------------------------------------------------------------------ #

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "schemas" / "agent-runtime"


_TASK_SPEC_VALIDATOR = load_offline_validator("task-spec.schema.json", SCHEMA_DIR)
_EXEC_REPORT_VALIDATOR = load_offline_validator("execution-report.schema.json", SCHEMA_DIR)


def _validate_task_spec(spec: dict) -> None:
    _TASK_SPEC_VALIDATOR.validate(spec)


def _validate_exec_report(report: dict) -> None:
    _EXEC_REPORT_VALIDATOR.validate(report)


# ------------------------------------------------------------------ #
# Fixtures / helpers
# ------------------------------------------------------------------ #

def _minimal_task_spec(**overrides) -> dict:
    spec: dict = {
        "task_id": "t-001",
        "title": "Test task",
        "priority": "P1",
        "status": "ready",
        "description": "Run read-only checks and report findings.",
    }
    spec.update(overrides)
    return spec


def _write_state(run_dir: Path, **fields) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(fields), encoding="utf-8")


def _human_required_workflow_profile() -> dict:
    return {
        "contract_version": "workflow-profile.v1",
        "resolver_version": "workflow-profile-resolver.v1",
        "profile_id": "unresolved",
        "profile_version": "1.0.0",
        "profile_fingerprint": f"sha256:{'0' * 64}",
        "work_type": "generic",
        "selection_source": "test fixture",
        "resolution_status": "human_required",
        "execution_state": "planned_only",
        "human_gate_required": True,
        "constraints": {
            "read_only": True,
            "network_enabled": False,
            "require_red_green_evidence": False,
        },
        "ordered_stages": [],
    }


def _executor_requirements() -> dict:
    return {
        "required_capabilities": ["filesystem.read", "execution.report"],
        "required_lifecycle_operations": ["launch", "collect"],
        "accepted_protocols": ["command", "acp"],
    }


def _executor_runtime(
    adapter_id: str = "fake-executor",
    *,
    quota_status: str = "available",
    blockers: list[dict] | None = None,
    identity_attestation: str = "verified",
) -> dict:
    return {
        "contract_version": "executor-contract.v1",
        "adapter_id": adapter_id,
        "adapter_version": "1.0.0",
        "protocol": {"name": "command", "version": "1"},
        "declared_capabilities": ["filesystem.read", "execution.report"],
        "negotiated_capabilities": ["filesystem.read", "execution.report"],
        "lifecycle": [
            {
                "phase": "launch",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:00Z",
            },
            {
                "phase": "collect",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:01Z",
            },
        ],
        "quota": {"status": quota_status, "unit": "tokens"},
        "blockers": blockers or [],
        "provenance": {
            "session_id": "session-1",
            "provider_requested": "provider-a",
            "provider_reported": "provider-a",
            "model_requested": "model-a",
            "model_reported": "model-a",
            "identity_attestation": identity_attestation,
        },
    }


def test_cross_file_executor_contract_refs_are_portable():
    task_spec = _minimal_task_spec(executor_requirements=_executor_requirements())
    contract = {
        "contract_version": "executor-contract.v1",
        "requirements": _executor_requirements(),
    }
    report = {
        "report_id": "report-1",
        "batch_id": "batch-1",
        "generated_at": "2026-07-23T00:00:00Z",
        "status": "fail",
        "summary": "Portable executor contract fixture.",
        "executor_runtime": _executor_runtime("portable-adapter"),
    }

    load_offline_validator("executor-contract.schema.json", SCHEMA_DIR).validate(contract)
    load_offline_validator("task-spec.schema.json", SCHEMA_DIR).validate(task_spec)
    load_offline_validator("execution-report.schema.json", SCHEMA_DIR).validate(report)


def test_offline_schema_loader_never_retrieves_network_resources(monkeypatch):
    import socket

    calls: list[tuple[object, ...]] = []

    def fail_if_networked(*args, **kwargs):
        calls.append(args)
        raise AssertionError("offline schema loader must not use the network")

    monkeypatch.setattr(socket, "create_connection", fail_if_networked)

    load_offline_validator("task-spec.schema.json", SCHEMA_DIR).validate(
        _minimal_task_spec(executor_requirements=_executor_requirements())
    )
    load_offline_validator("execution-report.schema.json", SCHEMA_DIR).validate(
        {
            "report_id": "report-1",
            "batch_id": "batch-1",
            "generated_at": "2026-07-23T00:00:00Z",
            "status": "fail",
            "summary": "Offline resolver test.",
            "executor_runtime": _executor_runtime(),
        }
    )

    assert calls == []


def test_offline_schema_loader_fails_closed_when_resource_is_missing(tmp_path):
    manifest = (SCHEMA_DIR / "offline-schema-registry.json").read_text(encoding="utf-8")
    (tmp_path / "offline-schema-registry.json").write_text(manifest, encoding="utf-8")

    with pytest.raises(AgentRuntimeSchemaError, match="sibling JSON file"):
        load_offline_validator("task-spec.schema.json", tmp_path)


def test_offline_schema_loader_rejects_rebound_manifest_uri(tmp_path):
    filenames = [
        "executor-contract.schema.json",
        "gate-result.schema.json",
        "task-spec.schema.json",
        "execution-report.schema.json",
    ]
    for filename in filenames:
        (tmp_path / filename).write_bytes((SCHEMA_DIR / filename).read_bytes())
    manifest = json.loads(
        (SCHEMA_DIR / "offline-schema-registry.json").read_text(encoding="utf-8")
    )
    manifest["resources"][1]["uri"] = "https://example.invalid/gate-result.schema.json"
    (tmp_path / "offline-schema-registry.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(AgentRuntimeSchemaError, match="canonical"):
        load_offline_validator("execution-report.schema.json", tmp_path)


def test_offline_schema_loader_dependencies_are_declared():
    pyproject = (
        REPO_ROOT / "packages" / "ai-workflow-hub" / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert '"jsonschema>=4.18,<5"' in pyproject
    assert '"referencing>=0.28,<1"' in pyproject


def test_offline_schema_loader_enforces_datetime_formats():
    report = {
        "report_id": "report-1",
        "batch_id": "batch-1",
        "generated_at": "not-a-timestamp",
        "status": "fail",
        "summary": "Format check fixture.",
    }

    with pytest.raises(ValidationError, match="date-time"):
        load_offline_validator("execution-report.schema.json", SCHEMA_DIR).validate(report)


class TestExecutorContractSemanticBoundaries:

    def test_malformed_lifecycle_operation_is_a_controlled_task_spec_error(self):
        spec = _minimal_task_spec(
            executor_requirements={
                "required_capabilities": ["filesystem.read"],
                "required_lifecycle_operations": [{"phase": "launch"}],
            }
        )

        with pytest.raises(TaskSpecValidationError, match="executor_requirements"):
            from_task_spec(spec)

    def test_negotiated_capabilities_must_be_declared(self):
        runtime = _executor_runtime()
        runtime["declared_capabilities"] = ["filesystem.read"]
        runtime["negotiated_capabilities"] = ["filesystem.write"]

        with pytest.raises(ExecutorContractValidationError, match="subset"):
            validate_executor_runtime(runtime)

    def test_lifecycle_timestamp_must_be_timezone_aware(self):
        runtime = _executor_runtime()
        runtime["lifecycle"][0]["observed_at"] = "2026-07-23T00:00:00"

        with pytest.raises(ExecutorContractValidationError, match="timezone"):
            validate_executor_runtime(runtime)

    @pytest.mark.parametrize(
        "field",
        ["declared_capabilities", "negotiated_capabilities", "lifecycle", "blockers"],
    )
    def test_runtime_arrays_have_bounded_cardinality(self, field):
        runtime = _executor_runtime()
        if field == "lifecycle":
            runtime[field] = [
                {
                    "phase": "launch",
                    "status": "completed",
                    "attempt": index + 1,
                    "observed_at": "2026-07-23T00:00:00Z",
                }
                for index in range(129)
            ]
        elif field == "blockers":
            runtime[field] = [
                {
                    "category": "environment",
                    "phase": "launch",
                    "retryable": False,
                    "reason": f"blocked-{index}",
                    "next_action": "Use a bounded retry.",
                }
                for index in range(65)
            ]
        else:
            capabilities = [f"capability-{index}" for index in range(65)]
            runtime[field] = capabilities
            runtime["declared_capabilities"] = list(capabilities)
            runtime["negotiated_capabilities"] = list(capabilities)

        with pytest.raises(ExecutorContractValidationError, match="at most"):
            validate_executor_runtime(runtime)


# ================================================================== #
# TaskSpec adapter -- positive
# ================================================================== #

class TestFromTaskSpecPositive:

    def test_returns_task_spec_and_operational(self):
        result = from_task_spec(_minimal_task_spec())
        assert "task_spec" in result
        assert "operational" in result

    def test_task_spec_is_canonical_closed(self):
        spec = _minimal_task_spec()
        result = from_task_spec(spec)
        assert result["task_spec"] == spec

    def test_operational_has_expected_keys(self):
        op = from_task_spec(_minimal_task_spec())["operational"]
        for key in (
            "title", "description", "risk",
            "allowed_files", "forbidden_files",
            "verification", "max_fix_rounds", "mode",
        ):
            assert key in op

    def test_envelope_provides_operational_values(self):
        envelope = {
            "allowed_files": ["a.py", "b.py"],
            "forbidden_files": ["c.py"],
            "verification": ["pytest"],
            "max_fix_rounds": 5,
            "mode": "apply",
        }
        op = from_task_spec(_minimal_task_spec(), envelope=envelope)["operational"]
        assert op["allowed_files"] == ["a.py", "b.py"]
        assert op["forbidden_files"] == ["c.py"]
        assert op["verification"] == ["pytest"]
        assert op["max_fix_rounds"] == 5
        assert op["mode"] == "apply"

    def test_allowed_files_from_conflict_registry_write_set(self):
        spec = _minimal_task_spec(
            conflict_registry={
                "read_set": ["x.py"],
                "write_set": ["a.py", "b.py"],
            },
        )
        op = from_task_spec(spec)["operational"]
        assert op["allowed_files"] == ["a.py", "b.py"]

    def test_envelope_allowed_files_overrides_conflict_registry(self):
        spec = _minimal_task_spec(
            conflict_registry={"read_set": [], "write_set": ["from_cr.py"]},
        )
        op = from_task_spec(
            spec, envelope={"allowed_files": ["from_env.py"]}
        )["operational"]
        assert op["allowed_files"] == ["from_env.py"]

    def test_priority_to_risk_mapping(self):
        for priority, risk in [
            ("P0", "high"), ("P1", "high"),
            ("P2", "medium"), ("P3", "low"),
        ]:
            op = from_task_spec(_minimal_task_spec(priority=priority))["operational"]
            assert op["risk"] == risk

    def test_defaults_without_envelope(self):
        op = from_task_spec(_minimal_task_spec())["operational"]
        assert op["mode"] == "dry-run"
        assert op["max_fix_rounds"] == 3
        assert op["forbidden_files"] == []
        assert op["verification"] == []
        assert op["allowed_files"] == []

    def test_task_spec_validates_with_jsonschema(self):
        spec = _minimal_task_spec(
            conflict_registry={"read_set": [], "write_set": ["a.py"]},
        )
        result = from_task_spec(spec)
        _validate_task_spec(result["task_spec"])

    def test_full_canonical_task_spec_validates(self):
        spec = _minimal_task_spec(
            depends_on=["t-000"],
            assumptions=["Assumption"],
            risk_notes="Low risk",
            estimated_tools=["Read", "Edit"],
            gate_0={
                "triggered": True,
                "trigger_reason": "test",
                "inventory_evidence": {
                    "queried_sources": ["src"],
                    "matched_capabilities": ["cap"],
                    "compared_against_request": ["req"],
                },
                "rules_checked": ["core-001"],
                "lessons_checked": ["LL-001"],
                "sufficiency_decision": "existing_partial",
                "decision": "build_delta",
                "delta_justification": "Need adapters",
            },
            conflict_registry={
                "read_set": ["src"],
                "write_set": ["a.py"],
                "protected_files_touched": False,
                "conflict_level": "low",
            },
        )
        result = from_task_spec(spec)
        _validate_task_spec(result["task_spec"])
        assert result["task_spec"] == spec

    def test_vendor_neutral_executor_requirements_and_workflow_profile_round_trip(self):
        spec = _minimal_task_spec(
            work_type="generic",
            workflow_profile=_human_required_workflow_profile(),
            executor_requirements=_executor_requirements(),
        )

        result = from_task_spec(spec)

        _validate_task_spec(result["task_spec"])
        assert result["task_spec"] == spec


# ================================================================== #
# TaskSpec adapter -- negative
# ================================================================== #

class TestFromTaskSpecNegative:

    def test_rejects_unknown_field(self):
        with pytest.raises(TaskSpecValidationError, match="(?i)unknown"):
            from_task_spec(_minimal_task_spec(scope=["a.py"]))

    def test_rejects_unknown_project_id(self):
        with pytest.raises(TaskSpecValidationError, match="(?i)unknown"):
            from_task_spec(_minimal_task_spec(project_id="my-proj"))

    def test_rejects_missing_required_field(self):
        spec = _minimal_task_spec()
        del spec["description"]
        with pytest.raises(TaskSpecValidationError, match="(?i)missing.*description"):
            from_task_spec(spec)

    def test_rejects_invalid_status(self):
        with pytest.raises(TaskSpecValidationError, match="(?i)status"):
            from_task_spec(_minimal_task_spec(status="unknown"))

    def test_rejects_invalid_priority(self):
        with pytest.raises(TaskSpecValidationError, match="(?i)priority"):
            from_task_spec(_minimal_task_spec(priority="P5"))

    def test_rejects_empty_description(self):
        with pytest.raises(TaskSpecValidationError, match="(?i)description"):
            from_task_spec(_minimal_task_spec(description=""))

    def test_rejects_empty_task_id(self):
        with pytest.raises(TaskSpecValidationError, match="(?i)task_id"):
            from_task_spec(_minimal_task_spec(task_id=""))

    def test_rejects_non_object(self):
        with pytest.raises(TaskSpecValidationError):
            from_task_spec("not a dict")  # type: ignore[arg-type]


# ================================================================== #
# ExecutionReport adapter -- positive
# ================================================================== #

class TestToExecutionReportPositive:

    def test_generates_required_fields(self, tmp_path):
        _write_state(tmp_path / "run", status="failed", task_id="t-1", run_id="r-1")
        report = to_execution_report(str(tmp_path / "run"))
        for field in ("report_id", "batch_id", "generated_at", "status", "summary"):
            assert field in report

    def test_failed_maps_to_fail(self, tmp_path):
        _write_state(tmp_path / "run", status="failed", task_id="t-1", run_id="r-1")
        assert to_execution_report(str(tmp_path / "run"))["status"] == "fail"

    def test_blocked_maps_to_blocked(self, tmp_path):
        _write_state(tmp_path / "run", status="blocked", task_id="t-1", run_id="r-1")
        assert to_execution_report(str(tmp_path / "run"))["status"] == "blocked"

    def test_human_required_maps_to_escalate(self, tmp_path):
        _write_state(tmp_path / "run", status="human_required", task_id="t-1", run_id="r-1")
        assert to_execution_report(str(tmp_path / "run"))["status"] == "escalate"

    def test_pass_with_full_evidence(self, tmp_path):
        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="passed", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1", reviewer_role="reviewer",
            review_result="pass",
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("# Review\nPass", encoding="utf-8")
        report = to_execution_report(str(run_dir))
        assert report["status"] == "pass"
        assert report["executor_id"] == "exec-1"
        ra = report["reviewer_artifacts"]
        assert ra["reviewer_id"] == "rev-1"
        assert ra["reviewer_role"] == "reviewer"
        assert ra["verdict"] == "pass"
        assert "review.yaml" in ra["review_yaml"]
        assert "review.md" in ra["review_md"]

    def test_validates_with_jsonschema(self, tmp_path):
        _write_state(
            tmp_path / "run",
            status="failed", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
        )
        _validate_exec_report(to_execution_report(str(tmp_path / "run")))

    def test_validates_pass_with_jsonschema(self, tmp_path):
        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="passed", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1", reviewer_role="reviewer",
            review_result="pass",
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")
        _validate_exec_report(to_execution_report(str(run_dir)))

    def test_no_unknown_fields(self, tmp_path):
        _write_state(tmp_path / "run", status="failed", task_id="t-1", run_id="r-1")
        report = to_execution_report(str(tmp_path / "run"))
        for old in (
            "task_id", "diff_summary", "test_results", "safety",
            "evidence_trust", "executed_nodes", "error_message",
            "fix_rounds", "changed_files",
        ):
            assert old not in report, f"old field '{old}' must not appear in canonical report"

    def test_run_ids_included(self, tmp_path):
        _write_state(tmp_path / "run", status="failed", task_id="t-1", run_id="r-1")
        assert to_execution_report(str(tmp_path / "run"))["run_ids"] == ["r-1"]

    def test_blocking_issues_for_failed(self, tmp_path):
        _write_state(
            tmp_path / "run",
            status="failed", task_id="t-1", run_id="r-1",
            error_message="Tests failed",
        )
        report = to_execution_report(str(tmp_path / "run"))
        assert len(report["blocking_issues"]) >= 1
        assert any("Tests failed" in s for s in report["blocking_issues"])

    def test_trust_record_from_backend_calls(self, tmp_path):
        _write_state(
            tmp_path / "run",
            status="passed", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1", reviewer_role="reviewer",
            review_result="pass",
            backend_calls={
                "executor": {
                    "backend": "opencode",
                    "session_id": "sess-abc",
                    "model": "deepseek/v4",
                    "tokens_used": 1200,
                },
            },
        )
        (run_dir := tmp_path / "run").mkdir(exist_ok=True)
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")
        report = to_execution_report(str(run_dir))
        assert report["trust_record"]["session_id"] == "sess-abc"
        assert report["trust_record"]["dispatch_method"] == "opencode"

    @pytest.mark.parametrize(
        "adapter_id",
        ["codex", "rd-code", "claude-code", "opencode", "future-executor"],
    )
    def test_vendor_neutral_executor_observation_validates(self, tmp_path, adapter_id):
        run_dir = tmp_path / adapter_id
        runtime = _executor_runtime(adapter_id)
        runtime["lifecycle"].append(
            {
                "phase": "cancel",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:02Z",
                "detail": "No active work remained.",
            }
        )
        _write_state(
            run_dir,
            status="failed",
            task_id="t-1",
            run_id=f"run-{adapter_id}",
            executor_id=f"executor-{adapter_id}",
            executor_runtime=runtime,
            backend_calls={
                "executor": {
                    "backend": adapter_id,
                    "session_id": "session-1",
                },
            },
        )

        report = to_execution_report(str(run_dir))

        _validate_exec_report(report)
        assert report["executor_runtime"] == runtime
        assert report["trust_record"]["dispatch_method"] == adapter_id


# ================================================================== #
# ExecutionReport adapter -- negative
# ================================================================== #

class TestToExecutionReportNegative:

    def test_pass_without_any_evidence_downgrades(self, tmp_path):
        _write_state(
            tmp_path / "run",
            status="passed", task_id="t-1", run_id="r-1",
        )
        report = to_execution_report(str(tmp_path / "run"))
        assert report["status"] == "blocked"
        issues = report.get("blocking_issues", [])
        assert any("executor" in s.lower() or "reviewer" in s.lower() for s in issues)

    def test_pass_with_executor_but_no_reviewer_downgrades(self, tmp_path):
        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="passed", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
        )
        report = to_execution_report(str(run_dir))
        assert report["status"] == "blocked"
        assert any("reviewer" in s.lower() for s in report.get("blocking_issues", []))

    def test_pass_with_reviewer_same_as_executor_downgrades(self, tmp_path):
        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="passed", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
            reviewer_id="exec-1",  # same!
            reviewer_role="reviewer",
            review_result="pass",
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")
        report = to_execution_report(str(run_dir))
        assert report["status"] == "blocked"

    def test_pass_with_exhausted_quota_downgrades_and_preserves_observation(self, tmp_path):
        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code", quota_status="exhausted")
        runtime["quota"]["retry_after_seconds"] = 300
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        report = to_execution_report(str(run_dir))

        _validate_exec_report(report)
        assert report["status"] == "blocked"
        assert report["executor_runtime"] == runtime
        assert any("quota" in issue.casefold() for issue in report["blocking_issues"])

    def test_pass_with_structured_blocker_downgrades(self, tmp_path):
        run_dir = tmp_path / "run"
        blocker = {
            "category": "toolchain",
            "phase": "launch",
            "retryable": True,
            "reason": "Required CLI is unavailable.",
            "next_action": "Install and re-run the executor preflight.",
        }
        runtime = _executor_runtime("codex", blockers=[blocker])
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        report = to_execution_report(str(run_dir))

        _validate_exec_report(report)
        assert report["status"] == "blocked"
        assert any("Required CLI" in issue for issue in report["blocking_issues"])

    def test_pass_with_identity_mismatch_downgrades(self, tmp_path):
        run_dir = tmp_path / "run"
        runtime = _executor_runtime("rd-code", identity_attestation="mismatch")
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        report = to_execution_report(str(run_dir))

        _validate_exec_report(report)
        assert report["status"] == "blocked"
        assert any("identity" in issue.casefold() for issue in report["blocking_issues"])

    def test_later_old_retry_event_cannot_override_highest_failed_attempt(self, tmp_path):
        """A reordered lifecycle stream must not turn a failed retry into a pass."""
        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"] = [
            {
                "phase": "launch",
                "status": "failed",
                "attempt": 2,
                "observed_at": "2026-07-23T00:00:02Z",
            },
            {
                "phase": "launch",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:01Z",
            },
            {
                "phase": "collect",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:03Z",
            },
        ]
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        report = to_execution_report(str(run_dir))

        assert report["status"] == "blocked"
        assert any("launch ended as failed" in issue.casefold() for issue in report["blocking_issues"])

    def test_same_attempt_newer_failure_cannot_be_overridden_by_older_event(self, tmp_path):
        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"] = [
            {
                "phase": "launch",
                "status": "failed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:02Z",
            },
            {
                "phase": "launch",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:01Z",
            },
        ]
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        report = to_execution_report(str(run_dir))

        assert report["status"] == "blocked"
        assert any("launch ended as failed" in issue.casefold() for issue in report["blocking_issues"])

    def test_conflicting_same_timestamp_lifecycle_events_downgrade(self, tmp_path):
        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"] = [
            {
                "phase": "launch",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:00Z",
            },
            {
                "phase": "launch",
                "status": "failed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:00Z",
            },
        ]
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        report = to_execution_report(str(run_dir))

        assert report["status"] == "blocked"
        assert any("conflicting terminal" in issue.casefold() for issue in report["blocking_issues"])

    def test_earlier_conflicting_lifecycle_events_cannot_be_cleared_by_later_completion(self, tmp_path):
        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"] = [
            {
                "phase": "launch",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:00Z",
            },
            {
                "phase": "launch",
                "status": "failed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:00Z",
            },
            {
                "phase": "launch",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:01Z",
            },
        ]
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        report = to_execution_report(str(run_dir))

        assert report["status"] == "blocked"
        assert any("conflicting terminal" in issue.casefold() for issue in report["blocking_issues"])

    def test_empty_batch_id_raises(self, tmp_path):
        _write_state(tmp_path / "run", status="failed")  # no task_id / run_id
        with pytest.raises(ExecutionReportError, match="(?i)batch_id"):
            to_execution_report(str(tmp_path / "run"))

    def test_explicit_empty_batch_id_raises(self, tmp_path):
        _write_state(tmp_path / "run", status="failed", task_id="t-1", run_id="r-1")
        with pytest.raises(ExecutionReportError, match="(?i)batch_id"):
            to_execution_report(str(tmp_path / "run"), batch_id="")


# ================================================================== #
# CLI _write_execution_report integration
# ================================================================== #

class TestWriteExecutionReportCLI:

    def test_writes_valid_json(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="failed", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
        )
        md_path = _write_execution_report(str(run_dir))
        assert md_path.endswith("execution-report.md")

        report = json.loads(
            (run_dir / "execution-report.json").read_text(encoding="utf-8")
        )
        _validate_exec_report(report)

    def test_markdown_reads_canonical_fields(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="blocked", task_id="t-1", run_id="r-1",
            executor_id="exec-1",
        )
        _write_execution_report(str(run_dir))
        md = (run_dir / "execution-report.md").read_text(encoding="utf-8")

        assert "report" in md.lower()
        assert "batch" in md.lower()
        assert "status" in md.lower()
        assert "summary" in md.lower()
        # Old field labels must NOT appear
        assert "diff_summary" not in md
        assert "evidence_trust" not in md

    def test_markdown_for_pass_downgrade_validates(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        _write_state(run_dir, status="passed", task_id="t-1", run_id="r-1")
        _write_execution_report(str(run_dir))
        report = json.loads(
            (run_dir / "execution-report.json").read_text(encoding="utf-8")
        )
        _validate_exec_report(report)
        assert report["status"] == "blocked"

    def test_exhausted_executor_quota_downgrades_on_real_report_path(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code", quota_status="exhausted")
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        _write_execution_report(str(run_dir))

        report = json.loads(
            (run_dir / "execution-report.json").read_text(encoding="utf-8")
        )
        _validate_exec_report(report)
        assert report["status"] == "blocked"
        assert report["executor_runtime"] == runtime

    def test_failed_lifecycle_downgrades_on_real_report_path(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"][-1]["status"] = "failed"
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        _write_execution_report(str(run_dir))

        report = json.loads(
            (run_dir / "execution-report.json").read_text(encoding="utf-8")
        )
        _validate_exec_report(report)
        assert report["status"] == "blocked"
        assert any("lifecycle" in issue.casefold() for issue in report["blocking_issues"])

    def test_reordered_lifecycle_retry_cannot_false_green_on_real_report_path(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"] = [
            {
                "phase": "launch",
                "status": "failed",
                "attempt": 2,
                "observed_at": "2026-07-23T00:00:02Z",
            },
            {
                "phase": "launch",
                "status": "completed",
                "attempt": 1,
                "observed_at": "2026-07-23T00:00:01Z",
            },
        ]
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        _write_execution_report(str(run_dir))

        report = json.loads(
            (run_dir / "execution-report.json").read_text(encoding="utf-8")
        )
        assert report["status"] == "blocked"
        assert any("launch ended as failed" in issue.casefold() for issue in report["blocking_issues"])

    def test_malformed_executor_runtime_is_rejected_before_report_write(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["blockers"] = "not-an-array"
        runtime["provenance"]["identity_attestation"] = "unrecognized"
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            executor_runtime=runtime,
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        with pytest.raises(ExecutionReportError, match="executor_runtime"):
            _write_execution_report(str(run_dir))

        assert not (run_dir / "execution-report.json").exists()

    def test_overlong_executor_identifier_is_rejected_before_report_write(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="failed",
            task_id="t-1",
            run_id="r-1",
            executor_runtime=_executor_runtime("a" * 129),
        )

        with pytest.raises(ExecutionReportError, match="executor_runtime"):
            _write_execution_report(str(run_dir))

        assert not (run_dir / "execution-report.json").exists()

    def test_malformed_lifecycle_is_rejected_before_report_write(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"] = [{"phase": "launch"}]
        _write_state(
            run_dir,
            status="failed",
            task_id="t-1",
            run_id="r-1",
            executor_runtime=runtime,
        )

        with pytest.raises(ExecutionReportError, match="executor_runtime"):
            _write_execution_report(str(run_dir))

        assert not (run_dir / "execution-report.json").exists()

    def test_invalid_dispatch_method_is_rejected_before_report_write(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            backend_calls={"executor": {"backend": "claude code"}},
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        with pytest.raises(ExecutionReportError, match="trust_record"):
            _write_execution_report(str(run_dir))

        assert not (run_dir / "execution-report.json").exists()

    def test_trust_record_personal_data_is_rejected_before_report_write(self, tmp_path):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="passed",
            task_id="t-1",
            run_id="r-1",
            executor_id="exec-1",
            reviewer_id="rev-1",
            reviewer_role="reviewer",
            review_result="pass",
            backend_calls={
                "executor": {
                    "backend": "portable-executor",
                    "session_id": "user@localhost",
                    "model": "C:/Users/Alice/private-model",
                },
            },
        )
        (run_dir / "review.yaml").write_text("verdict: pass", encoding="utf-8")
        (run_dir / "review.md").write_text("Pass", encoding="utf-8")

        with pytest.raises(ExecutionReportError, match="trust_record") as error:
            _write_execution_report(str(run_dir))

        assert "user@localhost" not in str(error.value)
        assert "C:/Users/Alice/private-model" not in str(error.value)
        assert not (run_dir / "execution-report.json").exists()
        assert not (run_dir / "execution-report.md").exists()

    @pytest.mark.parametrize(
        ("field", "value"),
        [("tokens_used", "many"), ("cost_estimate", -1)],
    )
    def test_trust_record_invalid_numeric_is_rejected_before_report_write(
        self, tmp_path, field, value
    ):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        _write_state(
            run_dir,
            status="failed",
            task_id="t-1",
            run_id="r-1",
            backend_calls={"executor": {"backend": "portable-executor", field: value}},
        )

        with pytest.raises(ExecutionReportError, match="trust_record"):
            _write_execution_report(str(run_dir))

        assert not (run_dir / "execution-report.json").exists()
        assert not (run_dir / "execution-report.md").exists()

    def test_configured_secret_in_runtime_observation_is_rejected_without_echo(
        self, tmp_path, monkeypatch
    ):
        from ai_workflow_hub.cli import _write_execution_report

        secret = "executor-secret-value-12345"
        monkeypatch.setenv("GENERIC_EXECUTOR_TOKEN", secret)
        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        runtime["lifecycle"][0]["detail"] = f"adapter output included {secret}"
        _write_state(
            run_dir,
            status="failed",
            task_id="t-1",
            run_id="r-1",
            executor_runtime=runtime,
        )

        with pytest.raises(ExecutionReportError, match="executor_runtime") as error:
            _write_execution_report(str(run_dir))

        assert secret not in str(error.value)
        assert not (run_dir / "execution-report.json").exists()

    @pytest.mark.parametrize("field", ["runtime", "trust_record"])
    def test_percent_encoded_configured_secret_is_rejected_before_report_write(
        self, tmp_path, monkeypatch, field
    ):
        from urllib.parse import quote

        from ai_workflow_hub.cli import _write_execution_report

        secret = "opaque%value?12345"
        encoded_secret = quote(secret, safe="")
        monkeypatch.setenv("GENERIC_EXECUTOR_TOKEN", secret)
        run_dir = tmp_path / "run"
        state = {
            "status": "failed",
            "task_id": "t-1",
            "run_id": "r-1",
        }
        if field == "runtime":
            runtime = _executor_runtime("claude-code")
            runtime["lifecycle"][0]["detail"] = encoded_secret
            state["executor_runtime"] = runtime
        else:
            state["backend_calls"] = {
                "executor": {
                    "backend": "portable-executor",
                    "session_id": encoded_secret,
                },
            }
        _write_state(run_dir, **state)

        with pytest.raises(ExecutionReportError) as error:
            _write_execution_report(str(run_dir))

        assert secret not in str(error.value)
        assert encoded_secret not in str(error.value)
        assert not (run_dir / "execution-report.json").exists()
        assert not (run_dir / "execution-report.md").exists()

    @pytest.mark.parametrize(
        ("field", "sensitive_value"),
        [
            ("lifecycle_detail", "contact user@example.com"),
            ("blocker_reason", "C:/Users/Alice/private"),
            ("provenance", "/home/alice/private"),
            ("lifecycle_detail", "password=raw-value-123"),
            ("blocker_reason", "https://user:raw-value@example.test/path"),
            ("provenance", "+1 (555) 123-4567"),
            ("lifecycle_detail", '"password"=raw-value-123'),
            ("blocker_reason", "/tmp"),
            ("provenance", "user@localhost"),
            ("lifecycle_detail", "https%3A%2F%2Fuser%3Araw-value%40example.test%2Fpath"),
        ],
    )
    def test_personal_data_or_local_path_is_rejected_before_json_or_markdown_write(
        self, tmp_path, field, sensitive_value
    ):
        from ai_workflow_hub.cli import _write_execution_report

        run_dir = tmp_path / "run"
        runtime = _executor_runtime("claude-code")
        if field == "lifecycle_detail":
            runtime["lifecycle"][0]["detail"] = sensitive_value
        elif field == "blocker_reason":
            runtime["blockers"] = [{
                "category": "environment",
                "phase": "launch",
                "retryable": False,
                "reason": sensitive_value,
                "next_action": "Use a safe diagnostic code.",
            }]
        else:
            runtime["provenance"]["provider_reported"] = sensitive_value
        _write_state(
            run_dir,
            status="failed",
            task_id="t-1",
            run_id="r-1",
            executor_runtime=runtime,
        )

        with pytest.raises(ExecutionReportError, match="executor_runtime") as error:
            _write_execution_report(str(run_dir))

        assert sensitive_value not in str(error.value)
        assert not (run_dir / "execution-report.json").exists()
        assert not (run_dir / "execution-report.md").exists()


# ================================================================== #
# CLI go_dispatch -- real-path unknown-field rejection
# ================================================================== #

class TestGoDispatchUnknownFieldRejection:
    """Real-path test: the CLI ``go`` command must not silently accept
    unknown TaskSpec fields.

    Previously ``go_dispatch`` pre-filtered ``raw_spec`` through
    ``CANONICAL_TASK_SPEC_FIELDS`` before validation, silently dropping
    typo/legacy/arbitrary fields and defeating
    ``additionalProperties: false``.  The fix passes the original
    TaskSpec directly to ``from_task_spec`` so unknown fields are
    rejected on the real path.
    """

    def test_unknown_field_rejected_on_real_cli_path(self, tmp_path):
        from ai_workflow_hub.cli import app
        from typer.testing import CliRunner

        spec = _minimal_task_spec(scope=["a.py"])
        spec_path = tmp_path / "task-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        result = CliRunner().invoke(
            app,
            ["go", str(spec_path)],
            env={"NO_COLOR": "1"},
        )

        assert result.exit_code != 0
        assert "unknown" in result.output.lower()

    def test_executor_requirements_survive_real_cli_dispatch(
        self, tmp_path, monkeypatch
    ):
        from ai_workflow_hub import cli
        from typer.testing import CliRunner

        spec = _minimal_task_spec(
            work_type="generic",
            workflow_profile=_human_required_workflow_profile(),
            executor_requirements=_executor_requirements(),
        )
        spec_path = tmp_path / "task-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        captured: dict = {}

        monkeypatch.setattr(cli, "init_env", lambda: None)
        monkeypatch.setattr(cli, "add_task", lambda *args, **kwargs: "task-1")

        def fake_execute_run(*args, **kwargs):
            captured["task_spec"] = kwargs.get("task_spec")
            return {"run_dir": ""}

        monkeypatch.setattr(cli, "_execute_run", fake_execute_run)

        result = CliRunner().invoke(
            cli.app,
            ["go", str(spec_path), "--project", "demo"],
            env={"NO_COLOR": "1"},
        )

        assert result.exit_code == 0, result.output
        assert captured["task_spec"] == spec

    @pytest.mark.parametrize(
        "requirements",
        [
            {
                "required_capabilities": "not-an-array",
                "required_lifecycle_operations": ["launch"],
            },
            {
                "required_capabilities": ["execution.report"],
                "required_lifecycle_operations": ["launch"],
                "accepted_protocols": ["bad protocol space"],
            },
            {
                "required_capabilities": ["a" * 129],
                "required_lifecycle_operations": ["launch"],
            },
            {
                "required_capabilities": [f"capability-{index}" for index in range(65)],
                "required_lifecycle_operations": ["launch"],
            },
        ],
    )
    def test_malformed_executor_requirements_are_rejected_before_cli_dispatch(
        self, tmp_path, monkeypatch, requirements
    ):
        from ai_workflow_hub import cli
        from typer.testing import CliRunner

        spec_path = tmp_path / "task-spec.json"
        spec_path.write_text(
            json.dumps(_minimal_task_spec(executor_requirements=requirements)),
            encoding="utf-8",
        )
        dispatched = False

        monkeypatch.setattr(cli, "init_env", lambda: None)

        def fail_if_dispatched(*args, **kwargs):
            nonlocal dispatched
            dispatched = True
            raise AssertionError("malformed TaskSpec must not be dispatched")

        monkeypatch.setattr(cli, "add_task", fail_if_dispatched)

        result = CliRunner().invoke(
            cli.app,
            ["go", str(spec_path), "--project", "demo"],
            env={"NO_COLOR": "1"},
        )

        assert result.exit_code != 0
        assert "executor_requirements" in result.output
        assert dispatched is False


# ================================================================== #
# Operational safety boundary -- apply mode requires a non-empty
# safety boundary (forbidden_files or verification).  R-004 regression.
# ================================================================== #

class TestApplyModeSafetyBoundary:
    """R-004: apply mode with an empty safety boundary is unsafe and must
    be rejected by ``from_task_spec`` on the real production path.

    Previously ``from_task_spec`` returned ``mode="dry-run"`` by default and
    the CLI ``--apply`` flag could flip it to apply while
    ``forbidden_files`` and ``verification`` remained empty, executing
    real changes with no declared safety boundary.  The fix makes
    ``from_task_spec`` reject apply mode when the safety boundary is
    empty (both ``forbidden_files`` and ``verification`` empty) unless
    a declared safety field is present.  Legitimate dry-run callers
    are unaffected.
    """

    def test_apply_mode_with_empty_boundary_is_rejected(self):
        with pytest.raises(TaskSpecValidationError, match="(?i)safety boundary"):
            from_task_spec(
                _minimal_task_spec(),
                envelope={"mode": "apply"},
            )

    def test_apply_mode_with_forbidden_files_is_accepted(self):
        op = from_task_spec(
            _minimal_task_spec(),
            envelope={"mode": "apply", "forbidden_files": ["secrets.py"]},
        )["operational"]
        assert op["mode"] == "apply"

    def test_apply_mode_with_verification_is_accepted(self):
        op = from_task_spec(
            _minimal_task_spec(),
            envelope={"mode": "apply", "verification": ["pytest"]},
        )["operational"]
        assert op["mode"] == "apply"

    def test_dry_run_mode_with_empty_boundary_is_preserved(self):
        """Legitimate dry-run callers must remain unaffected."""
        op = from_task_spec(_minimal_task_spec())["operational"]
        assert op["mode"] == "dry-run"
        assert op["forbidden_files"] == []
        assert op["verification"] == []

    def test_default_mode_with_empty_boundary_is_dry_run(self):
        op = from_task_spec(
            _minimal_task_spec(),
            envelope={},
        )["operational"]
        assert op["mode"] == "dry-run"


class TestGoDispatchApplySafetyBoundary:
    """R-004 real-path RED: the CLI ``go --apply`` path must reject a
    TaskSpec whose safety boundary is empty before dispatch.
    """

    def test_apply_with_empty_boundary_blocked_on_real_cli_path(self, tmp_path):
        from ai_workflow_hub.cli import app
        from typer.testing import CliRunner

        spec = _minimal_task_spec()
        spec_path = tmp_path / "task-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        result = CliRunner().invoke(
            app,
            ["go", str(spec_path), "--project", "demo", "--apply"],
            env={"NO_COLOR": "1"},
        )

        assert result.exit_code != 0
        assert "@go dispatch" not in result.output
