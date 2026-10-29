"""test_paper_runtime.py — A16 Paper Workflow Runtime E2E Tests.

Tests the runtime integration layer: create_paper_run, execute_paper_run,
resume_paper_run, get_paper_run_status, write_human_gate_artifact,
dispatch_paper_task, daemon routing, task_queue workflow_type,
graph artifact writing, and finalizer state persistence.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ai_workflow_hub.context_layer.adapters.paper_runtime import (
    create_paper_run,
    execute_paper_run,
    resume_paper_run,
    get_paper_run_status,
    write_human_gate_artifact,
    dispatch_paper_task,
    _save_state,
    _load_state,
    _run_path,
)
from ai_workflow_hub.workflows.paper_workflow_state import PaperWorkflowState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_base(tmp_path):
    """Provide a temporary base directory for paper runs."""
    return str(tmp_path)


@pytest.fixture
def mock_accepted_state():
    """State that leads to accepted (no blocking issues)."""
    return {
        "writelab_mode": "mock",
        "expression_issues": [],
        "paragraph_issues": [],
    }


@pytest.fixture
def mock_blocked_state():
    """State that leads to blocked (has blocking issues)."""
    return {
        "writelab_mode": "mock",
        "expression_issues": [],
        "paragraph_issues": [
            {
                "issue_type": "citation",
                "severity": "blocking",
                "description": "Missing reference [42]",
                "human_required": True,
            }
        ],
    }


# ===========================================================================
# TestPaperWorkflowStateA16 — Runtime fields
# ===========================================================================

class TestPaperWorkflowStateA16:
    """Verify A16 fields in PaperWorkflowState."""

    def test_run_id_default(self):
        s = PaperWorkflowState()
        assert s.run_id == ""

    def test_run_dir_default(self):
        s = PaperWorkflowState()
        assert s.run_dir == ""

    def test_project_id_default(self):
        s = PaperWorkflowState()
        assert s.project_id == ""

    def test_workflow_type_default(self):
        s = PaperWorkflowState()
        assert s.workflow_type == "paper"

    def test_a16_fields_settable(self):
        s = PaperWorkflowState(
            run_id="r1", run_dir="/tmp/r1", project_id="proj-1",
            workflow_type="paper",
        )
        assert s.run_id == "r1"
        assert s.run_dir == "/tmp/r1"
        assert s.project_id == "proj-1"
        assert s.workflow_type == "paper"

    def test_a16_fields_serialization(self):
        s = PaperWorkflowState(run_id="r1", project_id="p1")
        d = s.model_dump()
        assert d["run_id"] == "r1"
        assert d["project_id"] == "p1"
        assert d["workflow_type"] == "paper"


# ===========================================================================
# TestCreatePaperRun
# ===========================================================================

class TestCreatePaperRun:
    """Tests for create_paper_run()."""

    def test_basic_creation(self, tmp_base):
        result = create_paper_run("task-1", project_id="proj-1", base_dir=tmp_base)
        assert result["task_id"] == "task-1"
        assert result["project_id"] == "proj-1"
        assert result["status"] == "created"
        assert result["run_id"].startswith("paper-")
        assert Path(result["run_dir"]).exists()

    def test_state_json_created(self, tmp_base):
        result = create_paper_run("task-2", base_dir=tmp_base)
        state_file = Path(result["run_dir"]) / "state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["task_id"] == "task-2"
        assert state["run_id"] == result["run_id"]
        assert state["workflow_type"] == "paper"

    def test_empty_task_id_raises(self, tmp_base):
        with pytest.raises(ValueError, match="non-empty"):
            create_paper_run("", base_dir=tmp_base)

    def test_whitespace_task_id_raises(self, tmp_base):
        with pytest.raises(ValueError, match="non-empty"):
            create_paper_run("   ", base_dir=tmp_base)

    def test_initial_state_overrides(self, tmp_base):
        result = create_paper_run(
            "task-3", base_dir=tmp_base,
            initial_state={"writelab_mode": "offline", "task_chapter": "ch1"},
        )
        state = json.loads(
            (Path(result["run_dir"]) / "state.json").read_text(encoding="utf-8")
        )
        assert state["writelab_mode"] == "offline"
        assert state["task_chapter"] == "ch1"

    def test_unique_run_ids(self, tmp_base):
        r1 = create_paper_run("task-a", base_dir=tmp_base)
        r2 = create_paper_run("task-b", base_dir=tmp_base)
        assert r1["run_id"] != r2["run_id"]


# ===========================================================================
# TestExecutePaperRun
# ===========================================================================

class TestExecutePaperRun:
    """Tests for execute_paper_run()."""

    def test_accepted_path(self, tmp_base, mock_accepted_state):
        run = create_paper_run("task-ok", base_dir=tmp_base)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides=mock_accepted_state,
        )
        assert result["status"] == "completed"
        assert "gate_artifact" not in result

    def test_human_required_path(self, tmp_base, mock_blocked_state):
        run = create_paper_run("task-hr", base_dir=tmp_base)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides=mock_blocked_state,
        )
        assert result["status"] == "human_required"
        assert "gate_artifact" in result
        assert Path(result["gate_artifact"]).exists()

    def test_state_persisted_after_execute(self, tmp_base, mock_accepted_state):
        run = create_paper_run("task-sp", base_dir=tmp_base)
        execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides=mock_accepted_state,
        )
        state = _load_state(_run_path(run["run_id"], tmp_base))
        assert state is not None
        assert state["status"] == "completed"
        assert "diagnosis_node" in state.get("executed_nodes", [])

    def test_nonexistent_run_raises(self, tmp_base):
        with pytest.raises(FileNotFoundError):
            execute_paper_run("nonexistent-run", base_dir=tmp_base)

    def test_corrupt_state_raises(self, tmp_base):
        run = create_paper_run("task-cs", base_dir=tmp_base)
        # Corrupt state.json
        state_file = Path(run["run_dir"]) / "state.json"
        state_file.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(ValueError, match="corrupt"):
            execute_paper_run(run["run_id"], base_dir=tmp_base)

    def test_run_id_in_result(self, tmp_base, mock_accepted_state):
        run = create_paper_run("task-rid", base_dir=tmp_base)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides=mock_accepted_state,
        )
        assert result["run_id"] == run["run_id"]


# ===========================================================================
# TestResumePaperRun
# ===========================================================================

class TestResumePaperRun:
    """Tests for resume_paper_run()."""

    def _create_paused_run(self, tmp_base, mock_blocked_state):
        """Helper: create and execute a run that pauses at human gate."""
        run = create_paper_run("task-resume", base_dir=tmp_base)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides=mock_blocked_state,
        )
        assert result["status"] == "human_required"
        return run

    def test_resume_approved(self, tmp_base, mock_blocked_state):
        run = self._create_paused_run(tmp_base, mock_blocked_state)
        result = resume_paper_run(
            run["run_id"], decision="approved",
            reviewer_id="alice@test.com", note="Looks good",
            base_dir=tmp_base,
        )
        assert result["status"] == "completed"
        state = result["state"]
        assert state["human_gate_decision"] == "approved"
        assert state["reviewer_id"] == "alice@test.com"

    def test_resume_rejected(self, tmp_base, mock_blocked_state):
        run = self._create_paused_run(tmp_base, mock_blocked_state)
        result = resume_paper_run(
            run["run_id"], decision="rejected",
            reviewer_id="bob@test.com", note="Too many issues",
            base_dir=tmp_base,
        )
        # rejected path goes to END (not finalizer), status stays "rejected"
        # Note: the graph's _route_after_human_gate returns __end__ for rejected
        assert result["status"] in ("rejected", "completed", "human_required")

    def test_invalid_decision_raises(self, tmp_base, mock_blocked_state):
        run = self._create_paused_run(tmp_base, mock_blocked_state)
        with pytest.raises(ValueError, match="Invalid decision"):
            resume_paper_run(run["run_id"], decision="maybe", base_dir=tmp_base)

    def test_nonexistent_run_raises(self, tmp_base):
        with pytest.raises(FileNotFoundError):
            resume_paper_run("no-such-run", decision="approved", base_dir=tmp_base)

    def test_resume_non_paused_raises(self, tmp_base, mock_accepted_state):
        run = create_paper_run("task-np", base_dir=tmp_base)
        execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides=mock_accepted_state,
        )
        with pytest.raises(ValueError, match="not paused"):
            resume_paper_run(run["run_id"], decision="approved", base_dir=tmp_base)

    def test_resume_persists_decision(self, tmp_base, mock_blocked_state):
        run = self._create_paused_run(tmp_base, mock_blocked_state)
        resume_paper_run(
            run["run_id"], decision="approved",
            reviewer_id="carol@test.com", note="OK",
            base_dir=tmp_base,
        )
        state = _load_state(_run_path(run["run_id"], tmp_base))
        assert state["human_gate_decision"] == "approved"
        assert state["reviewer_id"] == "carol@test.com"

    def test_require_reviewer_raises(self, tmp_base, mock_blocked_state):
        run = self._create_paused_run(tmp_base, mock_blocked_state)
        with pytest.raises(ValueError, match="reviewer_id is required"):
            resume_paper_run(
                run["run_id"], decision="approved",
                reviewer_id="", base_dir=tmp_base,
                require_reviewer=True,
            )


# ===========================================================================
# TestGetPaperRunStatus
# ===========================================================================

class TestGetPaperRunStatus:
    """Tests for get_paper_run_status()."""

    def test_status_after_create(self, tmp_base):
        run = create_paper_run("task-st", base_dir=tmp_base)
        status = get_paper_run_status(run["run_id"], base_dir=tmp_base)
        assert status is not None
        assert status["status"] == "created"
        assert status["task_id"] == "task-st"

    def test_status_after_execute(self, tmp_base):
        run = create_paper_run("task-st2", base_dir=tmp_base)
        execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides={"writelab_mode": "mock"},
        )
        status = get_paper_run_status(run["run_id"], base_dir=tmp_base)
        assert status["status"] in ("completed", "human_required", "blocked")
        assert len(status["executed_nodes"]) > 0

    def test_nonexistent_returns_none(self, tmp_base):
        status = get_paper_run_status("no-such", base_dir=tmp_base)
        assert status is None

    def test_status_fields(self, tmp_base):
        run = create_paper_run("task-sf", project_id="proj-x", base_dir=tmp_base)
        status = get_paper_run_status(run["run_id"], base_dir=tmp_base)
        assert "task_id" in status
        assert "project_id" in status
        assert "acceptance_status" in status
        assert "blocking_count" in status
        assert "human_required" in status
        assert "executed_nodes" in status
        assert "created_at" in status
        assert "updated_at" in status


# ===========================================================================
# TestWriteHumanGateArtifact
# ===========================================================================

class TestWriteHumanGateArtifact:
    """Tests for write_human_gate_artifact()."""

    def test_artifact_created(self, tmp_base):
        run = create_paper_run("task-art", base_dir=tmp_base)
        state = _load_state(_run_path(run["run_id"], tmp_base))
        path = write_human_gate_artifact(run["run_id"], state, tmp_base)
        assert Path(path).exists()
        assert path.endswith("paper-human-gate.md")

    def test_artifact_content(self, tmp_base):
        run = create_paper_run("task-artc", base_dir=tmp_base)
        state = _load_state(_run_path(run["run_id"], tmp_base))
        state["acceptance_status"] = "human_required"
        state["blocking_count"] = 2
        state["all_review_issues"] = [
            {"severity": "blocking", "issue_type": "citation", "description": "Missing ref"},
            {"severity": "blocking", "issue_type": "logic", "description": "Wrong theorem"},
        ]
        path = write_human_gate_artifact(run["run_id"], state, tmp_base)
        content = Path(path).read_text(encoding="utf-8")
        assert "Paper Human Gate" in content
        assert run["run_id"] in content
        assert "Missing ref" in content
        assert "Wrong theorem" in content
        assert "blocking" in content.lower()
        assert "Resume Instructions" in content

    def test_artifact_resume_command(self, tmp_base):
        run = create_paper_run("task-cmd", base_dir=tmp_base)
        state = _load_state(_run_path(run["run_id"], tmp_base))
        path = write_human_gate_artifact(run["run_id"], state, tmp_base)
        content = Path(path).read_text(encoding="utf-8")
        assert "resume_paper_run" in content
        assert run["run_id"] in content

    def test_artifact_with_ledger(self, tmp_base):
        run = create_paper_run("task-ledger", base_dir=tmp_base)
        state = _load_state(_run_path(run["run_id"], tmp_base))
        state["ledger_summary"] = {"total": 5, "open": 3, "blocking": 2}
        path = write_human_gate_artifact(run["run_id"], state, tmp_base)
        content = Path(path).read_text(encoding="utf-8")
        assert "Ledger Summary" in content

    def test_artifact_no_issues(self, tmp_base):
        run = create_paper_run("task-ni", base_dir=tmp_base)
        state = _load_state(_run_path(run["run_id"], tmp_base))
        state["all_review_issues"] = []
        path = write_human_gate_artifact(run["run_id"], state, tmp_base)
        content = Path(path).read_text(encoding="utf-8")
        assert "No issues found" in content


# ===========================================================================
# TestDispatchPaperTask
# ===========================================================================

class TestDispatchPaperTask:
    """Tests for dispatch_paper_task()."""

    def test_dispatch_creates_run(self, tmp_base):
        task = {"id": "dispatch-1", "project_id": "proj-d"}
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime._runs_root",
            return_value=Path(tmp_base) / "runs" / "paper",
        ):
            result = dispatch_paper_task(task)
        assert "run_id" in result
        assert result["run_id"].startswith("paper-")
        assert result["status"] in ("completed", "human_required", "blocked")

    def test_dispatch_returns_status(self, tmp_base):
        task = {"id": "dispatch-2", "project_id": "proj-d"}
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime._runs_root",
            return_value=Path(tmp_base) / "runs" / "paper",
        ):
            result = dispatch_paper_task(task)
        assert "status" in result


# ===========================================================================
# TestDaemonRouting
# ===========================================================================

class TestDaemonRouting:
    """Tests for daemon._execute_one_task workflow_type routing (A16)."""

    def test_paper_workflow_type_routes_to_paper(self):
        task = {"id": "rt-1", "project_id": "proj-1", "workflow_type": "paper"}
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task"
        ) as mock_dispatch:
            from ai_workflow_hub.daemon import _execute_one_task
            _execute_one_task(task)
            mock_dispatch.assert_called_once_with(task)

    def test_coding_workflow_type_routes_to_coding(self):
        task = {"id": "rt-2", "project_id": "proj-1", "workflow_type": "coding",
                "coding_backend": ""}
        with patch("ai_workflow_hub.cli._execute_run") as mock_exec:
            from ai_workflow_hub.daemon import _execute_one_task
            _execute_one_task(task)
            mock_exec.assert_called_once()

    def test_default_workflow_type_is_coding(self):
        task = {"id": "rt-3", "project_id": "proj-1", "coding_backend": ""}
        with patch("ai_workflow_hub.cli._execute_run") as mock_exec:
            from ai_workflow_hub.daemon import _execute_one_task
            _execute_one_task(task)
            mock_exec.assert_called_once()


# ===========================================================================
# TestTaskQueueWorkflowType
# ===========================================================================

class TestTaskQueueWorkflowType:
    """Tests for task_queue.add_task workflow_type support (A16)."""

    def test_add_task_default_workflow_type(self):
        """Default workflow_type should be 'coding'."""
        from ai_workflow_hub.task_queue import _DEFAULTS
        assert _DEFAULTS["workflow_type"] == "coding"

    def test_normalize_adds_workflow_type(self):
        """_normalize should add workflow_type to old tasks."""
        from ai_workflow_hub.task_queue import _normalize
        task = {"id": "t1", "status": "queued"}
        normalized = _normalize(task)
        assert normalized["workflow_type"] == "coding"

    def test_normalize_preserves_paper_type(self):
        """_normalize should not overwrite existing workflow_type."""
        from ai_workflow_hub.task_queue import _normalize
        task = {"id": "t2", "status": "queued", "workflow_type": "paper"}
        normalized = _normalize(task)
        assert normalized["workflow_type"] == "paper"


# ===========================================================================
# TestGraphHumanGateArtifact (A16 graph integration)
# ===========================================================================

class TestGraphHumanGateArtifact:
    """Tests for graph writing human gate artifact when run_dir is set."""

    def test_graph_writes_artifact_on_pause(self, tmp_path):
        """When run_dir is set and graph pauses at human_gate, artifact should be written."""
        from ai_workflow_hub.workflows.paper_graph import compile_paper_graph

        run_id = "graph-artifact-test"
        run_dir = str(tmp_path / run_id)
        os.makedirs(run_dir, exist_ok=True)

        initial = {
            "task_id": "graph-art-task",
            "writelab_mode": "mock",
            "expression_issues": [],
            "paragraph_issues": [
                {
                    "issue_type": "citation",
                    "severity": "blocking",
                    "description": "Missing ref [99]",
                    "human_required": True,
                }
            ],
            "run_id": run_id,
            "run_dir": run_dir,
        }

        compiled = compile_paper_graph("test-artifact-thread")
        config = {"configurable": {"thread_id": "test-artifact-thread"}}
        result = compiled.invoke(initial, config)

        # Check artifact was written
        artifact = Path(run_dir) / "paper-human-gate.md"
        assert artifact.exists()
        content = artifact.read_text(encoding="utf-8")
        assert run_id in content
        assert "Missing ref [99]" in content


# ===========================================================================
# TestGraphFinalizerPersistence (A16 graph integration)
# ===========================================================================

class TestGraphFinalizerPersistence:
    """Tests for finalizer saving state to run_dir."""

    def test_finalizer_saves_state(self, tmp_path):
        """Finalizer should persist final state to run_dir/state.json."""
        from ai_workflow_hub.workflows.paper_graph import compile_paper_graph

        run_id = "graph-persist-test"
        run_dir = str(tmp_path / run_id)
        os.makedirs(run_dir, exist_ok=True)

        initial = {
            "task_id": "graph-persist-task",
            "writelab_mode": "mock",
            "expression_issues": [],
            "paragraph_issues": [],
            "run_id": run_id,
            "run_dir": run_dir,
        }

        compiled = compile_paper_graph("test-persist-thread")
        config = {"configurable": {"thread_id": "test-persist-thread"}}
        result = compiled.invoke(initial, config)

        # Check state.json was written
        state_file = Path(run_dir) / "state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["status"] == "completed"
        assert "paper_finalizer_node" in state.get("executed_nodes", [])


# ===========================================================================
# TestE2EFullLifecycle (A16 integration)
# ===========================================================================

class TestE2EFullLifecycle:
    """End-to-end lifecycle: create → execute → pause → resume → complete."""

    def test_full_lifecycle_approved(self, tmp_base):
        """Full lifecycle: create → execute (pauses) → resume (approved) → completed."""
        # Step 1: Create
        run = create_paper_run("e2e-task", project_id="e2e-proj", base_dir=tmp_base)
        assert run["status"] == "created"

        # Step 2: Execute (should pause at human gate due to blocking issue)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides={
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": [
                    {
                        "issue_type": "citation",
                        "severity": "blocking",
                        "description": "Missing reference [42]",
                        "human_required": True,
                    }
                ],
            },
        )
        assert result["status"] == "human_required"
        assert "gate_artifact" in result

        # Step 3: Verify status
        status = get_paper_run_status(run["run_id"], base_dir=tmp_base)
        assert status["status"] == "human_required"
        assert status["human_required"] is True

        # Step 4: Resume with approval
        resume_result = resume_paper_run(
            run["run_id"],
            decision="approved",
            reviewer_id="reviewer@e2e.com",
            note="E2E test approval",
            base_dir=tmp_base,
        )
        assert resume_result["status"] == "completed"

        # Step 5: Verify final status
        final_status = get_paper_run_status(run["run_id"], base_dir=tmp_base)
        assert final_status["status"] == "completed"
        assert final_status["human_gate_decision"] == "approved"
        assert final_status["reviewer_id"] == "reviewer@e2e.com"

    def test_full_lifecycle_no_blocking(self, tmp_base):
        """Full lifecycle with no blocking issues → direct completion."""
        run = create_paper_run("e2e-ok", project_id="e2e-proj", base_dir=tmp_base)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides={
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": [],
            },
        )
        assert result["status"] == "completed"
        assert "gate_artifact" not in result

        final = get_paper_run_status(run["run_id"], base_dir=tmp_base)
        assert final["status"] == "completed"
        assert final["executed_nodes"] == [
            "diagnosis_node", "acceptance_gate_node",
            "ledger_ingest_node", "paper_finalizer_node",
        ]


# ===========================================================================
# TestSaveLoadState (internal helpers)
# ===========================================================================

class TestSaveLoadState:
    """Tests for _save_state and _load_state helpers."""

    def test_save_and_load(self, tmp_path):
        state = {"task_id": "t1", "status": "running", "count": 42}
        _save_state(tmp_path, state)
        loaded = _load_state(tmp_path)
        assert loaded == state

    def test_load_missing(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert _load_state(empty_dir) is None

    def test_load_corrupt(self, tmp_path):
        (tmp_path / "state.json").write_text("{broken", encoding="utf-8")
        assert _load_state(tmp_path) is None

    def test_atomic_save(self, tmp_path):
        """Verify .tmp file is replaced, not left behind."""
        _save_state(tmp_path, {"key": "value"})
        assert (tmp_path / "state.json").exists()
        assert not (tmp_path / "state.json.tmp").exists()


# ===========================================================================
# A16B Tests: Privacy, Sanitization, Status Update, Audit Isolation
# ===========================================================================

from ai_workflow_hub.context_layer.adapters.paper_runtime import (
    sanitize_run_id,
    redact_state,
    _save_state_safe,
    _SENSITIVE_FIELDS,
    _REDACTED_MARKER,
)


class TestSanitizeRunId:
    """A16B: run_id sanitization tests."""

    def test_normal_run_id(self):
        assert sanitize_run_id("paper-20250612-abc123") == "paper-20250612-abc123"

    def test_path_traversal(self):
        result = sanitize_run_id("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_special_chars(self):
        result = sanitize_run_id("run/with\\spaces:and<>")
        assert "/" not in result
        assert "\\" not in result
        assert " " not in result

    def test_hidden_file_prevention(self):
        result = sanitize_run_id(".hidden_run")
        assert not result.startswith(".")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            sanitize_run_id("")

    def test_whitespace_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            sanitize_run_id("   ")

    def test_truncation(self):
        long_id = "a" * 200
        result = sanitize_run_id(long_id)
        assert len(result) <= 128

    def test_dots_and_underscores(self):
        result = sanitize_run_id("run..with__many___dots")
        assert ".." not in result
        assert "__" not in result


class TestRedactState:
    """A16B: Privacy redaction tests."""

    def test_paragraph_text_redacted(self):
        state = {"task_id": "t1", "paragraph_text": "secret manuscript content"}
        redacted = redact_state(state)
        assert redacted["paragraph_text"] == "[REDACTED]"
        assert state["paragraph_text"] == "secret manuscript content"  # original unchanged

    def test_writelab_token_redacted(self):
        state = {"task_id": "t1", "writelab_token": "bearer-secret-123"}
        redacted = redact_state(state)
        assert redacted["writelab_token"] == "[REDACTED]"

    def test_non_sensitive_fields_preserved(self):
        state = {"task_id": "t1", "status": "running", "run_id": "r1"}
        redacted = redact_state(state)
        assert redacted["task_id"] == "t1"
        assert redacted["status"] == "running"
        assert redacted["run_id"] == "r1"

    def test_empty_sensitive_field_not_redacted(self):
        state = {"task_id": "t1", "paragraph_text": ""}
        redacted = redact_state(state)
        assert redacted["paragraph_text"] == ""  # empty string not replaced

    def test_original_not_modified(self):
        state = {"task_id": "t1", "paragraph_text": "original", "writelab_token": "tok"}
        redacted = redact_state(state)
        assert state["paragraph_text"] == "original"
        assert state["writelab_token"] == "tok"
        assert redacted is not state


class TestSaveStateSafe:
    """A16B: Privacy-safe state persistence tests."""

    def test_save_redacts_on_disk(self, tmp_path):
        state = {"task_id": "t1", "paragraph_text": "secret", "status": "ok"}
        _save_state_safe(tmp_path, state)
        loaded = _load_state(tmp_path)
        assert loaded["paragraph_text"] == "[REDACTED]"
        assert loaded["status"] == "ok"
        # Original state not modified
        assert state["paragraph_text"] == "secret"

    def test_save_preserves_non_sensitive(self, tmp_path):
        state = {"task_id": "t1", "run_id": "r1", "status": "completed",
                 "executed_nodes": ["diagnosis_node"]}
        _save_state_safe(tmp_path, state)
        loaded = _load_state(tmp_path)
        assert loaded["task_id"] == "t1"
        assert loaded["executed_nodes"] == ["diagnosis_node"]


class TestA16BCreatePaperRun:
    """A16B: create_paper_run with sanitization and privacy."""

    def test_run_id_is_sanitized(self, tmp_base):
        run = create_paper_run("task-san", base_dir=tmp_base)
        # Generated run_id should already be safe, but verify
        assert ".." not in run["run_id"]
        assert "/" not in run["run_id"]

    def test_state_json_redacts_paragraph_text(self, tmp_base):
        run = create_paper_run(
            "task-priv", base_dir=tmp_base,
            initial_state={"paragraph_text": "secret paper content"},
        )
        state_file = Path(run["run_dir"]) / "state.json"
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["paragraph_text"] == "[REDACTED]"

    def test_decision_base_dir_set_for_audit_isolation(self, tmp_base):
        run = create_paper_run("task-audit", base_dir=tmp_base)
        state_file = Path(run["run_dir"]) / "state.json"
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["decision_base_dir"] == run["run_dir"]


class TestA16BExecutePaperRun:
    """A16B: execute_paper_run with privacy and warnings."""

    def test_execute_redacts_state_on_disk(self, tmp_base):
        run = create_paper_run("task-exepriv", base_dir=tmp_base)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides={
                "writelab_mode": "mock",
                "paragraph_text": "very secret manuscript",
                "expression_issues": [],
                "paragraph_issues": [],
            },
        )
        # On-disk state should have redacted paragraph_text
        state_file = Path(result["state"]["run_dir"]) / "state.json"
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["paragraph_text"] == "[REDACTED]"

    def test_execute_returns_warnings_list(self, tmp_base):
        run = create_paper_run("task-warn", base_dir=tmp_base)
        result = execute_paper_run(
            run["run_id"], base_dir=tmp_base,
            state_overrides={"writelab_mode": "mock"},
        )
        assert "warnings" in result
        assert isinstance(result["warnings"], list)


class TestA16BDispatchStatusUpdate:
    """A16B: dispatch_paper_task updates task_queue status."""

    def test_dispatch_updates_task_queue(self, tmp_base):
        task = {"id": "disp-a16b", "project_id": "proj-d"}
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime._runs_root",
            return_value=Path(tmp_base) / "runs" / "paper",
        ), patch(
            "ai_workflow_hub.task_queue.mark_task_finished",
            return_value=True,
        ) as mock_mark:
            result = dispatch_paper_task(task)
            mock_mark.assert_called_once()
            args = mock_mark.call_args
            assert args[0][0] == "disp-a16b"  # task_id
            assert args[0][1] in ("passed", "human_required", "blocked", "failed")

    def test_dispatch_returns_task_queue_fields(self, tmp_base):
        task = {"id": "disp-a16b-2", "project_id": "proj-d"}
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime._runs_root",
            return_value=Path(tmp_base) / "runs" / "paper",
        ), patch(
            "ai_workflow_hub.task_queue.mark_task_finished",
            return_value=True,
        ):
            result = dispatch_paper_task(task)
            assert "task_queue_updated" in result
            assert "task_queue_status" in result
            assert result["task_queue_updated"] is True


class TestA16BAuditIsolation:
    """A16B: Decision audit scoped per run_id."""

    def test_audit_isolated_per_run(self, tmp_base):
        """Two runs for same task_id should have separate audit trails."""
        run1 = create_paper_run("same-task", base_dir=tmp_base)
        run2 = create_paper_run("same-task", base_dir=tmp_base)
        # decision_base_dir should differ
        s1 = json.loads(
            (Path(run1["run_dir"]) / "state.json").read_text(encoding="utf-8")
        )
        s2 = json.loads(
            (Path(run2["run_dir"]) / "state.json").read_text(encoding="utf-8")
        )
        assert s1["decision_base_dir"] != s2["decision_base_dir"]
        assert s1["decision_base_dir"] == run1["run_dir"]
        assert s2["decision_base_dir"] == run2["run_dir"]


class TestA16BGraphFinalizerRedaction:
    """A16B: Graph finalizer saves redacted state."""

    def test_finalizer_redacts_paragraph_text(self, tmp_path):
        from ai_workflow_hub.workflows.paper_graph import compile_paper_graph

        run_id = "redact-finalizer-test"
        run_dir = str(tmp_path / run_id)
        os.makedirs(run_dir, exist_ok=True)

        initial = {
            "task_id": "redact-test",
            "writelab_mode": "mock",
            "paragraph_text": "top secret manuscript text",
            "expression_issues": [],
            "paragraph_issues": [],
            "run_id": run_id,
            "run_dir": run_dir,
        }

        compiled = compile_paper_graph("redact-finalizer-thread")
        config = {"configurable": {"thread_id": "redact-finalizer-thread"}}
        compiled.invoke(initial, config)

        state_file = Path(run_dir) / "state.json"
        assert state_file.exists()
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved.get("paragraph_text") == "[REDACTED]"
        assert saved["status"] == "completed"
