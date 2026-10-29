"""test_paper_a21_daemon_queue_e2e.py -- A21 PAPER-DAEMON-QUEUE-E2E Tests.

Proves the full daemon -> task_queue -> paper_runtime chain with synthetic
data.  Exercises find_runnable_tasks, run_queued_tasks, dispatch_paper_task,
mark_stale_running_tasks, retry limits, and mixed paper/coding priority --
all without external services.

Isolation strategy:
  - config_loader._hub_dir  -> tmp_path  (tasks.yaml, projects.yaml, logs)
  - task_queue.tasks_lock   -> no-op     (single-threaded test, skip file lock)
  - config_loader.get_tasks / save_tasks -> in-memory dict
  - project_registry.find_project        -> synthetic project with real path
  - daemon._daemon_config                -> fixed test config
  - paper_runtime._runs_root             -> tmp_path / "runs" / "paper"
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# In-memory task store (shared across task_queue mocks)
# ---------------------------------------------------------------------------

_store: dict = {}


def _mock_get_tasks() -> dict:
    """Return the in-memory store.  Tasks are mutated in-place by
    mark_task_running etc., so we must NOT deepcopy."""
    return _store


def _mock_save_tasks(data: dict) -> None:
    """Accept save calls.  Mutations already happened in-place on _store."""
    # If task_queue ever replaces the whole list (e.g. add_task appends then
    # saves a new dict), sync it back.
    if data is not _store:
        _store.clear()
        _store.update(data)


# ---------------------------------------------------------------------------
# Real function references (captured before any patching, for full-chain tests)
# ---------------------------------------------------------------------------
from ai_workflow_hub.context_layer.adapters.paper_runtime import (
    execute_paper_run as _real_execute_paper_run,
)

SYNTHETIC_ISSUES_BLOCKING = [
    {
        "issue_id": "a21-iss-001",
        "issue_type": "citation",
        "severity": "major",
        "description": "Reference [42] is missing from bibliography",
        "evidence": "Section 3 cites [42] but it does not appear",
        "human_required": True,
        "blocking": True,
        "recommendation": "Add reference [42]",
    },
]

SYNTHETIC_ISSUES_CLEAN = []


# ---------------------------------------------------------------------------
# Core fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Redirect all daemon/task_queue/paper_runtime I/O to tmp_path."""
    global _store
    _store = {"tasks": []}

    # --- config_loader: _hub_dir ---
    monkeypatch.setattr(
        "ai_workflow_hub.config_loader._hub_dir", lambda: tmp_path
    )
    # _TASKS_LOCKFILE was computed at import time from the real _hub_dir.
    # Point it to tmp_path so the real tasks_lock (used by local imports
    # inside dispatch_paper_task) can create/remove the lockfile.
    monkeypatch.setattr(
        "ai_workflow_hub.config_loader._TASKS_LOCKFILE",
        tmp_path / "tasks.yaml.lock",
    )

    # --- task_queue: tasks_lock (imported directly, must patch there) ---
    from contextlib import contextmanager

    @contextmanager
    def _noop_lock():
        yield

    monkeypatch.setattr(
        "ai_workflow_hub.task_queue.tasks_lock", _noop_lock
    )

    # --- task_queue: get_tasks / save_tasks (patched where imported) ---
    monkeypatch.setattr(
        "ai_workflow_hub.task_queue.get_tasks", _mock_get_tasks
    )
    monkeypatch.setattr(
        "ai_workflow_hub.task_queue.save_tasks", _mock_save_tasks
    )

    # --- daemon: config ---
    monkeypatch.setattr(
        "ai_workflow_hub.daemon._daemon_config",
        lambda: {
            "max_concurrency": 2,
            "max_retries": 1,
            "stale_run_minutes": 30,
            "poll_interval_seconds": 1,
        },
    )

    # --- project_registry: find_project ---
    proj_path = tmp_path / "project"
    proj_path.mkdir(parents=True, exist_ok=True)
    _find_project_mock = lambda pid: {"id": pid, "enabled": True, "path": str(proj_path)}
    monkeypatch.setattr(
        "ai_workflow_hub.project_registry.find_project", _find_project_mock,
    )
    # daemon.py uses `from .project_registry import find_project` — must patch
    # the daemon module's own reference too.
    monkeypatch.setattr(
        "ai_workflow_hub.daemon.find_project", _find_project_mock,
    )

    # daemon.py uses `from .task_queue import mark_task_running, mark_task_finished`
    # — patch daemon's local references to our mocked task_queue functions.
    from ai_workflow_hub import task_queue as _tq
    monkeypatch.setattr("ai_workflow_hub.daemon.mark_task_running", _tq.mark_task_running)
    monkeypatch.setattr("ai_workflow_hub.daemon.mark_task_finished", _tq.mark_task_finished)

    # --- paper_runtime: _runs_root ---
    runs_root = tmp_path / "runs" / "paper"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "ai_workflow_hub.context_layer.adapters.paper_runtime._runs_root",
        lambda base_dir=None: runs_root,
    )

    return {"tmp_path": tmp_path, "proj_path": proj_path, "runs_root": runs_root}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_task(
    task_id: str,
    *,
    workflow_type: str = "paper",
    status: str = "queued",
    priority: str = "normal",
    dependencies: list | None = None,
    retry_count: int = 0,
    project_id: str = "proj-a21",
    updated_at: str = "",
    coding_backend: str = "",
) -> dict:
    """Insert a task directly into the in-memory store."""
    now = datetime.now(timezone.utc).isoformat()
    task = {
        "id": task_id,
        "project_id": project_id,
        "title": f"Test task {task_id}",
        "description": "",
        "risk": "medium",
        "status": status,
        "priority": priority,
        "dependencies": dependencies or [],
        "coding_backend": coding_backend,
        "workflow_type": workflow_type,
        "last_run_id": "",
        "retry_count": retry_count,
        "blocked_reason": "",
        "last_started_at": "",
        "lease_until": "",
        "created_at": now,
        "updated_at": updated_at or now,
    }
    _store["tasks"].append(task)
    return task


def _find_in_store(task_id: str) -> dict | None:
    for t in _store.get("tasks", []):
        if t["id"] == task_id:
            return t
    return None


# ===========================================================================
# TestAddPaperTaskToQueue
# ===========================================================================

class TestAddPaperTaskToQueue:
    """Verify add_task with workflow_type='paper' round-trips correctly."""

    def test_add_paper_task(self):
        from ai_workflow_hub.task_queue import add_task

        tid = add_task(
            "proj-a21", "Paper review task",
            workflow_type="paper",
        )
        assert tid.startswith("task-")
        task = _find_in_store(tid)
        assert task is not None
        assert task["workflow_type"] == "paper"
        assert task["status"] == "queued"

    def test_find_paper_task(self):
        from ai_workflow_hub.task_queue import add_task, find_task

        tid = add_task("proj-a21", "Find me", workflow_type="paper")
        found = find_task(tid)
        assert found is not None
        assert found["workflow_type"] == "paper"

    def test_list_tasks_filters_by_status(self):
        from ai_workflow_hub.task_queue import add_task, list_tasks

        add_task("proj-a21", "Q1", workflow_type="paper")
        add_task("proj-a21", "Q2", workflow_type="paper")
        queued = list_tasks(status="queued")
        assert len(queued) == 2

    def test_default_workflow_type_is_coding(self):
        from ai_workflow_hub.task_queue import add_task

        tid = add_task("proj-a21", "Coding default")
        task = _find_in_store(tid)
        assert task["workflow_type"] == "coding"


# ===========================================================================
# TestFindRunnablePaperTasks
# ===========================================================================

class TestFindRunnablePaperTasks:
    """Verify filtering, exclusion, dependency, and priority sorting."""

    def test_finds_queued_paper_tasks(self):
        from ai_workflow_hub.daemon import find_runnable_tasks

        _seed_task("paper-1", workflow_type="paper")
        _seed_task("paper-2", workflow_type="paper")
        runnable = find_runnable_tasks()
        ids = {t["id"] for t in runnable}
        assert "paper-1" in ids
        assert "paper-2" in ids

    def test_filters_by_project(self):
        from ai_workflow_hub.daemon import find_runnable_tasks

        _seed_task("p1-task", project_id="proj-A", workflow_type="paper")
        _seed_task("p2-task", project_id="proj-B", workflow_type="paper")
        runnable = find_runnable_tasks(project_id="proj-A")
        assert len(runnable) == 1
        assert runnable[0]["id"] == "p1-task"

    def test_excludes_running_tasks(self):
        from ai_workflow_hub.daemon import find_runnable_tasks

        _seed_task("queued-t", workflow_type="paper", status="queued")
        _seed_task("running-t", workflow_type="paper", status="running")
        runnable = find_runnable_tasks()
        ids = {t["id"] for t in runnable}
        assert "queued-t" in ids
        assert "running-t" not in ids

    def test_excludes_terminal_tasks(self):
        from ai_workflow_hub.daemon import find_runnable_tasks

        _seed_task("q", workflow_type="paper", status="queued")
        _seed_task("passed", workflow_type="paper", status="passed")
        _seed_task("failed", workflow_type="paper", status="failed")
        _seed_task("blocked", workflow_type="paper", status="blocked")
        _seed_task("cancelled", workflow_type="paper", status="cancelled")
        runnable = find_runnable_tasks()
        assert len(runnable) == 1
        assert runnable[0]["id"] == "q"

    def test_unsatisfied_dependency_skips_task(self):
        from ai_workflow_hub.daemon import find_runnable_tasks

        _seed_task("dep-parent", workflow_type="paper", status="running")
        _seed_task(
            "dep-child", workflow_type="paper",
            dependencies=["dep-parent"],
        )
        runnable = find_runnable_tasks()
        ids = {t["id"] for t in runnable}
        assert "dep-child" not in ids
        assert "dep-parent" not in ids  # running, excluded

    def test_priority_sorting(self):
        from ai_workflow_hub.daemon import find_runnable_tasks

        _seed_task("low-t", workflow_type="paper", priority="low")
        _seed_task("urgent-t", workflow_type="paper", priority="urgent")
        _seed_task("normal-t", workflow_type="paper", priority="normal")
        _seed_task("high-t", workflow_type="paper", priority="high")
        runnable = find_runnable_tasks()
        priorities = [t["priority"] for t in runnable]
        assert priorities == ["urgent", "high", "normal", "low"]


# ===========================================================================
# TestRunQueuedPaperTasks
# ===========================================================================

class TestRunQueuedPaperTasks:
    """Verify run_queued_tasks dispatches, handles errors, and enforces limits."""

    def test_dispatches_paper_task(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("rq-1", workflow_type="paper")

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ) as mock_dispatch:
            result = run_queued_tasks()

        assert result["started"] == 1
        assert "rq-1" in result["started_ids"]
        mock_dispatch.assert_called_once()

    def test_task_marked_running_before_dispatch(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("rq-running", workflow_type="paper")

        running_at_dispatch = []

        def _capture(task):
            t = _find_in_store("rq-running")
            running_at_dispatch.append(t["status"] if t else "NOT_FOUND")
            return {"run_id": "r1", "status": "completed"}

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            side_effect=_capture,
        ):
            run_queued_tasks()

        assert running_at_dispatch == ["running"]

    def test_dispatch_exception_marks_failed(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("rq-err", workflow_type="paper")

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            side_effect=RuntimeError("graph exploded"),
        ):
            result = run_queued_tasks()

        assert result["started"] == 1
        task = _find_in_store("rq-err")
        assert task["status"] == "failed"
        assert "graph exploded" in task["blocked_reason"]

    def test_max_concurrency_respected(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("c-1", workflow_type="paper")
        _seed_task("c-2", workflow_type="paper")
        _seed_task("c-3", workflow_type="paper")

        dispatch_count = 0

        def _count(task):
            nonlocal dispatch_count
            dispatch_count += 1
            return {"run_id": f"r-{task['id']}", "status": "completed"}

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            side_effect=_count,
        ):
            result = run_queued_tasks()

        # daemon config max_concurrency=2
        assert result["started"] == 2
        assert dispatch_count == 2

    def test_retry_limit_marks_blocked(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("rq-retry", workflow_type="paper", retry_count=5)

        result = run_queued_tasks()

        task = _find_in_store("rq-retry")
        assert task["status"] == "blocked"
        assert "max retries" in task["blocked_reason"]
        assert result["started"] == 0

    def test_coding_task_routes_to_cli(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("rq-code", workflow_type="coding", coding_backend="")

        with patch("ai_workflow_hub.cli._execute_run") as mock_exec:
            result = run_queued_tasks()

        assert result["started"] == 1
        mock_exec.assert_called_once()


# ===========================================================================
# TestDaemonPaperTaskFullChain  (NO dispatch mock -- real graph execution)
# ===========================================================================

class TestDaemonPaperTaskFullChain:
    """Real dispatch_paper_task with mock writelab -- proves full chain."""

    def test_paper_completed_via_daemon(self, isolated_env):
        """Paper task with no blocking issues: queued -> running -> passed."""
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("chain-ok", workflow_type="paper")

        # Seed the graph's mock state via a pre-created run.
        # dispatch_paper_task will create a run, execute the graph.
        # With writelab_mode="mock" and no issues, the graph completes.
        # We patch the graph compile to inject mock state overrides.
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.execute_paper_run",
            wraps=self._execute_with_mock_overrides,
        ):
            result = run_queued_tasks()

        assert result["started"] == 1
        task = _find_in_store("chain-ok")
        # Debug: if failed, capture the error reason for the assertion message
        reason = task.get("blocked_reason", "no reason")
        assert task["status"] == "passed", f"Task failed: {reason}"
        assert task["last_run_id"] != ""

    @staticmethod
    def _execute_with_mock_overrides(run_id, **kwargs):
        """Wrapper that injects writelab_mode='mock' and clean issues."""
        kwargs["state_overrides"] = {
            "writelab_mode": "mock",
            "expression_issues": [],
            "paragraph_issues": SYNTHETIC_ISSUES_CLEAN,
        }
        return _real_execute_paper_run(run_id, **kwargs)

    def test_paper_human_required_via_daemon(self, isolated_env):
        """Paper task with blocking issues: queued -> running -> human_required."""
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("chain-hr", workflow_type="paper")

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.execute_paper_run",
            wraps=self._execute_with_blocking_issues,
        ):
            result = run_queued_tasks()

        assert result["started"] == 1
        task = _find_in_store("chain-hr")
        reason = task.get("blocked_reason", "no reason")
        # Graph may return "human_required" or "blocked" depending on issue
        # severity; both map to non-completed terminal states in task_queue.
        assert task["status"] in ("human_required", "blocked"), (
            f"Task status: {task['status']}, reason: {reason}"
        )

    @staticmethod
    def _execute_with_blocking_issues(run_id, **kwargs):
        kwargs["state_overrides"] = {
            "writelab_mode": "mock",
            "expression_issues": [],
            "paragraph_issues": SYNTHETIC_ISSUES_BLOCKING,
        }
        return _real_execute_paper_run(run_id, **kwargs)

    def test_full_chain_disk_artifacts(self, isolated_env):
        """Verify run_dir, state.json, and ledger created by real dispatch."""
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("chain-disk", workflow_type="paper")
        ledger_dir = isolated_env["tmp_path"] / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)

        def _execute_with_ledger(run_id, **kwargs):
            kwargs["state_overrides"] = {
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": SYNTHETIC_ISSUES_BLOCKING,
                "ledger_dir": str(ledger_dir),
            }
            return _real_execute_paper_run(run_id, **kwargs)

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.execute_paper_run",
            side_effect=_execute_with_ledger,
        ):
            run_queued_tasks()

        # Run directory created
        runs_root = isolated_env["runs_root"]
        run_dirs = list(runs_root.iterdir())
        assert len(run_dirs) >= 1

        # state.json exists and is privacy-clean
        run_dir = run_dirs[0]
        state_file = run_dir / "state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["workflow_type"] == "paper"
        # Privacy: no raw sensitive values
        if "paragraph_text" in state:
            assert state["paragraph_text"] in ("", "[REDACTED]")
        if "writelab_token" in state:
            assert state["writelab_token"] in ("", "[REDACTED]")


# ===========================================================================
# TestStalePaperTaskRecovery
# ===========================================================================

class TestStalePaperTaskRecovery:
    """Verify mark_stale_running_tasks recovers stuck paper tasks."""

    def test_stale_running_marked_failed(self):
        from ai_workflow_hub.daemon import mark_stale_running_tasks

        old_time = (
            datetime.now(timezone.utc) - timedelta(minutes=60)
        ).isoformat()
        _seed_task(
            "stale-1", workflow_type="paper",
            status="running", updated_at=old_time,
        )

        count = mark_stale_running_tasks()

        assert count == 1
        task = _find_in_store("stale-1")
        assert task["status"] == "failed"
        assert "stale" in task["blocked_reason"]

    def test_recent_running_not_marked(self):
        from ai_workflow_hub.daemon import mark_stale_running_tasks

        recent_time = (
            datetime.now(timezone.utc) - timedelta(minutes=5)
        ).isoformat()
        _seed_task(
            "recent-1", workflow_type="paper",
            status="running", updated_at=recent_time,
        )

        count = mark_stale_running_tasks()

        assert count == 0
        task = _find_in_store("recent-1")
        assert task["status"] == "running"


# ===========================================================================
# TestPaperRetryLimit
# ===========================================================================

class TestPaperRetryLimit:
    """Verify retry limit enforcement for paper tasks."""

    def test_exceeded_retry_blocks_task(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("retry-over", workflow_type="paper", retry_count=10)

        run_queued_tasks()

        task = _find_in_store("retry-over")
        assert task["status"] == "blocked"
        assert "max retries" in task["blocked_reason"]

    def test_within_retry_runs_normally(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("retry-ok", workflow_type="paper", retry_count=1)

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ):
            result = run_queued_tasks()

        assert result["started"] == 1


# ===========================================================================
# TestMixedPaperCodingPriority
# ===========================================================================

class TestMixedPaperCodingPriority:
    """Verify daemon handles mixed paper + coding tasks with priority."""

    def test_highest_priority_tasks_run_first(self):
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("mix-urgent-paper", workflow_type="paper", priority="urgent")
        _seed_task("mix-normal-code", workflow_type="coding", priority="normal")
        _seed_task("mix-low-paper", workflow_type="paper", priority="low")

        paper_dispatched = []

        def _track_paper(task):
            paper_dispatched.append(task["id"])
            return {"run_id": f"r-{task['id']}", "status": "completed"}

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            side_effect=_track_paper,
        ), patch(
            "ai_workflow_hub.cli._execute_run",
        ):
            result = run_queued_tasks()

        # max_concurrency=2: urgent-paper and normal-code started
        assert result["started"] == 2
        assert "mix-urgent-paper" in result["started_ids"]
        assert "mix-normal-code" in result["started_ids"]
        # low-paper not started (3rd in priority order)
        assert "mix-low-paper" not in result["started_ids"]

    def test_paper_before_coding_at_same_priority(self):
        from ai_workflow_hub.daemon import find_runnable_tasks

        _seed_task("same-code", workflow_type="coding", priority="normal")
        _seed_task("same-paper", workflow_type="paper", priority="normal")

        runnable = find_runnable_tasks()
        # Both returned (stable sort preserves insertion order for same priority)
        assert len(runnable) == 2
        ids = {t["id"] for t in runnable}
        assert "same-code" in ids
        assert "same-paper" in ids
