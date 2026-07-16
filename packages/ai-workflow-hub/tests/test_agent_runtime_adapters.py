"""TDD tests for canonical TaskSpec / ExecutionReport adapters.

These tests drive the RED -> GREEN cycle for aligning
``task_spec_adapter`` and ``execution_report_adapter`` with the
canonical closed schemas in ``schemas/agent-runtime/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_workflow_hub.task_spec_adapter import (
    TaskSpecValidationError,
    from_task_spec,
)
from ai_workflow_hub.execution_report_adapter import (
    ExecutionReportError,
    to_execution_report,
)

# ------------------------------------------------------------------ #
# Canonical schema loading (from repo, never weakened)
# ------------------------------------------------------------------ #

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "schemas" / "agent-runtime"


def _load_json(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8-sig"))


_TASK_SPEC_SCHEMA = _load_json("task-spec.schema.json")
_EXEC_REPORT_SCHEMA = _load_json("execution-report.schema.json")
_GATE_RESULT_SCHEMA = _load_json("gate-result.schema.json")


def _exec_report_schema_inlined() -> dict:
    """Return the execution-report schema with the gate-result $ref inlined.

    The canonical schema references ``./gate-result.schema.json`` via
    ``$ref``.  We inline it so jsonschema validation works without a
    network/file resolver, while still loading both canonical schemas
    from the repo.
    """
    schema = json.loads(json.dumps(_EXEC_REPORT_SCHEMA))
    schema["properties"]["gate_results"]["items"] = json.loads(
        json.dumps(_GATE_RESULT_SCHEMA)
    )
    return schema


_ER_SCHEMA = _exec_report_schema_inlined()


def _validate_task_spec(spec: dict) -> None:
    Draft202012Validator(_TASK_SPEC_SCHEMA).validate(spec)


def _validate_exec_report(report: dict) -> None:
    Draft202012Validator(_ER_SCHEMA).validate(report)


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
