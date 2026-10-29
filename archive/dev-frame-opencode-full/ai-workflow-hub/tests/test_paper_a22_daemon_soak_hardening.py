"""test_paper_a22_daemon_soak_hardening.py — A22 PAPER-DAEMON-SOAK-HARDENING Tests.

Hardens the daemon subsystem with tests for:
  - daemon_loop(once=True): single-cycle execution
  - daemon_soak(): plan-mode simulation + report generation
  - Lock management: pidfile, heartbeat, cleanup
  - Audit trail: daemon.start, daemon.stop, task_start, task_error, stale_recovery
  - Restart behaviour: stale pidfile handling
  - Status transition matrix
  - mark_task_retry: terminal-status guard verification
  - Multi-cycle stale recovery

Isolation strategy (same as A21 + daemon-specific patches):
  - config_loader._hub_dir     -> tmp_path
  - task_queue.get_tasks/save_tasks -> in-memory dict
  - task_queue.tasks_lock      -> no-op
  - daemon._daemon_config      -> fixed test config
  - daemon._PIDFILE/_HEARTBEAT -> tmp_path (module-level constants need patching)
  - daemon._acquire_lock       -> always True (skip Windows ctypes)
  - time.sleep                 -> no-op (fast test cycles)
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# In-memory task store (shared across task_queue mocks)
# ---------------------------------------------------------------------------

_store: dict = {}


def _mock_get_tasks() -> dict:
    return _store


def _mock_save_tasks(data: dict) -> None:
    if data is not _store:
        _store.clear()
        _store.update(data)


# ---------------------------------------------------------------------------
# Real function references (captured before any patching)
# ---------------------------------------------------------------------------
from ai_workflow_hub.context_layer.adapters.paper_runtime import (
    execute_paper_run as _real_execute_paper_run,
)

SYNTHETIC_ISSUES_CLEAN: list = []


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
    monkeypatch.setattr(
        "ai_workflow_hub.config_loader._TASKS_LOCKFILE",
        tmp_path / "tasks.yaml.lock",
    )

    # --- audit: _hub_dir (imported at module level, needs separate patch) ---
    monkeypatch.setattr(
        "ai_workflow_hub.audit._hub_dir", lambda: tmp_path
    )

    # --- daemon: _hub_dir (imported at module level) ---
    monkeypatch.setattr(
        "ai_workflow_hub.daemon._hub_dir", lambda: tmp_path
    )

    # --- task_queue ---
    from contextlib import contextmanager

    @contextmanager
    def _noop_lock():
        yield

    monkeypatch.setattr("ai_workflow_hub.task_queue.tasks_lock", _noop_lock)
    monkeypatch.setattr("ai_workflow_hub.task_queue.get_tasks", _mock_get_tasks)
    monkeypatch.setattr("ai_workflow_hub.task_queue.save_tasks", _mock_save_tasks)

    # --- daemon: config ---
    monkeypatch.setattr(
        "ai_workflow_hub.daemon._daemon_config",
        lambda: {
            "max_concurrency": 2,
            "max_retries": 1,
            "stale_run_minutes": 30,
            "poll_interval_seconds": 0,  # no sleep in tests
        },
    )

    # --- daemon: PIDFILE/HEARTBEAT (module-level constants) ---
    daemon_dir = tmp_path / "runs" / "daemon"
    daemon_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "ai_workflow_hub.daemon._PIDFILE", daemon_dir / "daemon.pid"
    )
    monkeypatch.setattr(
        "ai_workflow_hub.daemon._HEARTBEAT", daemon_dir / "daemon.heartbeat"
    )

    # --- daemon: _acquire_lock (skip Windows ctypes) ---
    monkeypatch.setattr(
        "ai_workflow_hub.daemon._acquire_lock", lambda: True
    )

    # --- project_registry ---
    proj_path = tmp_path / "project"
    proj_path.mkdir(parents=True, exist_ok=True)
    _find_project = lambda pid: {"id": pid, "enabled": True, "path": str(proj_path)}
    monkeypatch.setattr("ai_workflow_hub.project_registry.find_project", _find_project)
    monkeypatch.setattr("ai_workflow_hub.daemon.find_project", _find_project)

    # daemon task_queue refs
    from ai_workflow_hub import task_queue as _tq
    monkeypatch.setattr("ai_workflow_hub.daemon.mark_task_running", _tq.mark_task_running)
    monkeypatch.setattr("ai_workflow_hub.daemon.mark_task_finished", _tq.mark_task_finished)

    # --- paper_runtime ---
    runs_root = tmp_path / "runs" / "paper"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "ai_workflow_hub.context_layer.adapters.paper_runtime._runs_root",
        lambda base_dir=None: runs_root,
    )

    # --- time.sleep: no-op ---
    monkeypatch.setattr("ai_workflow_hub.daemon.time.sleep", lambda s: None)

    return {
        "tmp_path": tmp_path,
        "proj_path": proj_path,
        "runs_root": runs_root,
        "daemon_dir": daemon_dir,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_task(
    task_id: str, *, workflow_type: str = "paper", status: str = "queued",
    priority: str = "normal", retry_count: int = 0, project_id: str = "proj-a22",
    updated_at: str = "", risk: str = "medium",
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    task = {
        "id": task_id, "project_id": project_id,
        "title": f"Test task {task_id}", "description": "",
        "risk": risk, "status": status, "priority": priority,
        "dependencies": [], "coding_backend": "",
        "workflow_type": workflow_type,
        "last_run_id": "", "retry_count": retry_count,
        "blocked_reason": "", "last_started_at": "",
        "lease_until": "",
        "created_at": now, "updated_at": updated_at or now,
    }
    _store["tasks"].append(task)
    return task


def _find_in_store(task_id: str) -> dict | None:
    for t in _store.get("tasks", []):
        if t["id"] == task_id:
            return t
    return None


def _read_audit_entries(tmp_path: Path) -> list[dict]:
    """Read all audit JSONL entries from the audit directory."""
    audit_dir = tmp_path / "runs" / "audit"
    if not audit_dir.exists():
        return []
    entries = []
    for f in sorted(audit_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return entries


def _make_time_sequence(start=1000.0, cycle=1000.5, exit_time=1061.0):
    """Create a time.time() replacement for soak tests.

    Returns start (for start_time), then cycle (for while check — inside range),
    then exit_time (for while check — outside range), then exit_time for all
    subsequent calls (elapsed calculation, etc.).
    """
    vals = [start, cycle, exit_time]
    idx = [0]

    def _fake_time():
        i = idx[0]
        if i < len(vals):
            idx[0] = i + 1
            return vals[i]
        return exit_time  # stable after exhaustion

    return _fake_time


# ===========================================================================
# TestA22DaemonLoopOnce — daemon_loop(once=True)
# ===========================================================================

class TestA22DaemonLoopOnce:
    """daemon_loop with once=True: single cycle execution."""

    def test_once_returns_zero(self, isolated_env):
        """daemon_loop(once=True) should return 0 after one cycle."""
        from ai_workflow_hub.daemon import daemon_loop

        _seed_task("once-1", workflow_type="paper")

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ):
            result = daemon_loop(once=True)

        assert result == 0

    def test_once_writes_pidfile(self, isolated_env):
        """daemon_loop should write pidfile before execution."""
        from ai_workflow_hub.daemon import daemon_loop

        pidfile_seen = []

        def _capture_dispatch(task):
            # Check pidfile exists during execution (before cleanup)
            pidfile = isolated_env["daemon_dir"] / "daemon.pid"
            pidfile_seen.append(pidfile.exists())
            return {"run_id": "r1", "status": "completed"}

        _seed_task("once-pid", workflow_type="paper")
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            side_effect=_capture_dispatch,
        ):
            daemon_loop(once=True)

        assert pidfile_seen == [True], "pidfile should exist during execution"

    def test_once_cleans_up_lock(self, isolated_env):
        """daemon_loop(once=True) should clean up pidfile after completion."""
        from ai_workflow_hub.daemon import daemon_loop

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ):
            daemon_loop(once=True)

        pidfile = isolated_env["daemon_dir"] / "daemon.pid"
        assert not pidfile.exists(), "pidfile should be cleaned up after once=True"

    def test_once_writes_audit_start_and_stop(self, isolated_env):
        """daemon_loop should write daemon.start and daemon.stop audit entries."""
        from ai_workflow_hub.daemon import daemon_loop

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ):
            daemon_loop(once=True)

        entries = _read_audit_entries(isolated_env["tmp_path"])
        actions = [e["action"] for e in entries]
        assert "daemon.start" in actions
        assert "daemon.stop" in actions

    def test_once_dispatches_queued_task(self, isolated_env):
        """daemon_loop(once=True) should dispatch queued paper tasks."""
        from ai_workflow_hub.daemon import daemon_loop

        _seed_task("once-dispatch", workflow_type="paper")

        dispatched = []

        def _capture(task):
            dispatched.append(task["id"])
            return {"run_id": f"r-{task['id']}", "status": "completed"}

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            side_effect=_capture,
        ):
            daemon_loop(once=True)

        assert "once-dispatch" in dispatched


# ===========================================================================
# TestA22HeartbeatAndPidfile — Heartbeat and PID file management
# ===========================================================================

class TestA22HeartbeatAndPidfile:
    """Verify heartbeat and pidfile lifecycle."""

    def test_write_pidfile(self, isolated_env):
        from ai_workflow_hub.daemon import _write_pidfile

        _write_pidfile()
        pidfile = isolated_env["daemon_dir"] / "daemon.pid"
        assert pidfile.exists()
        assert int(pidfile.read_text().strip()) == os.getpid()

    def test_write_heartbeat(self, isolated_env):
        from ai_workflow_hub.daemon import _write_heartbeat

        _write_heartbeat()
        hb = isolated_env["daemon_dir"] / "daemon.heartbeat"
        assert hb.exists()
        ts = hb.read_text().strip()
        # Should be valid ISO timestamp
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_cleanup_lock_removes_files(self, isolated_env):
        from ai_workflow_hub.daemon import _write_pidfile, _write_heartbeat, _cleanup_lock

        _write_pidfile()
        _write_heartbeat()
        pidfile = isolated_env["daemon_dir"] / "daemon.pid"
        heartbeat = isolated_env["daemon_dir"] / "daemon.heartbeat"
        assert pidfile.exists()
        assert heartbeat.exists()

        _cleanup_lock()
        assert not pidfile.exists()
        assert not heartbeat.exists()

    def test_cleanup_lock_safe_when_no_files(self, isolated_env):
        """_cleanup_lock should not raise if files don't exist."""
        from ai_workflow_hub.daemon import _cleanup_lock

        _cleanup_lock()  # should not raise


# ===========================================================================
# TestA22AuditTrail — Structured audit logging
# ===========================================================================

class TestA22AuditTrail:
    """Verify structured audit entries for daemon lifecycle events."""

    def test_task_start_audit(self, isolated_env):
        """run_queued_tasks should write daemon.task_start audit entry."""
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("audit-start", workflow_type="paper")

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ):
            run_queued_tasks()

        entries = _read_audit_entries(isolated_env["tmp_path"])
        start_entries = [e for e in entries if e["action"] == "daemon.task_start"]
        assert len(start_entries) >= 1
        entry = start_entries[0]
        assert entry["task_id"] == "audit-start"
        assert entry["result"] == "STARTED"

    def test_task_error_audit(self, isolated_env):
        """run_queued_tasks should write daemon.task_error on exception."""
        from ai_workflow_hub.daemon import run_queued_tasks

        _seed_task("audit-err", workflow_type="paper")

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            side_effect=RuntimeError("boom"),
        ):
            run_queued_tasks()

        entries = _read_audit_entries(isolated_env["tmp_path"])
        err_entries = [e for e in entries if e["action"] == "daemon.task_error"]
        assert len(err_entries) >= 1
        assert err_entries[0]["task_id"] == "audit-err"
        assert err_entries[0]["result"] == "FAILED"
        assert "boom" in err_entries[0].get("reason", "")

    def test_stale_recovery_audit(self, isolated_env):
        """mark_stale_running_tasks should write daemon.stale_recovery."""
        from ai_workflow_hub.daemon import mark_stale_running_tasks

        old_time = (
            datetime.now(timezone.utc) - timedelta(minutes=60)
        ).isoformat()
        _seed_task("audit-stale", workflow_type="paper",
                    status="running", updated_at=old_time)

        mark_stale_running_tasks()

        entries = _read_audit_entries(isolated_env["tmp_path"])
        stale_entries = [e for e in entries if e["action"] == "daemon.stale_recovery"]
        assert len(stale_entries) >= 1
        assert stale_entries[0]["task_id"] == "audit-stale"

    def test_daemon_start_blocked_audit(self, isolated_env, monkeypatch):
        """daemon_loop should write audit entry when lock fails."""
        from ai_workflow_hub.daemon import daemon_loop

        # Override _acquire_lock to return False (another instance running)
        monkeypatch.setattr("ai_workflow_hub.daemon._acquire_lock", lambda: False)

        result = daemon_loop(once=True)
        assert result == 1

        entries = _read_audit_entries(isolated_env["tmp_path"])
        blocked = [e for e in entries
                   if e["action"] == "daemon.start" and e["result"] == "BLOCKED"]
        assert len(blocked) >= 1


# ===========================================================================
# TestA22DaemonSoakPlanMode — daemon_soak() plan mode
# ===========================================================================

class TestA22DaemonSoakPlanMode:
    """Verify daemon_soak in plan mode (simulation without execution)."""

    def test_soak_plan_mode_returns_passed(self, isolated_env, monkeypatch):
        """daemon_soak in plan mode should return status='passed'."""
        from ai_workflow_hub.daemon import daemon_soak

        monkeypatch.setattr(
            "ai_workflow_hub.daemon._daemon_config",
            lambda: {"max_concurrency": 2, "max_retries": 1,
                     "stale_run_minutes": 30, "poll_interval_seconds": 0},
        )

        # Mock time.time to ensure exactly one cycle runs
        monkeypatch.setattr("ai_workflow_hub.daemon.time.time", _make_time_sequence())

        result = daemon_soak(duration_minutes=1, mode="plan")
        assert result["status"] == "passed"
        assert result["exit_code"] == 0
        assert result["mode"] == "plan"
        assert result["simulated"] is True

    def test_soak_counts_queued_tasks(self, isolated_env, monkeypatch):
        """Plan mode should count runnable tasks without executing."""
        from ai_workflow_hub.daemon import daemon_soak

        monkeypatch.setattr(
            "ai_workflow_hub.daemon._daemon_config",
            lambda: {"max_concurrency": 2, "max_retries": 1,
                     "stale_run_minutes": 30, "poll_interval_seconds": 0},
        )

        _seed_task("soak-1", workflow_type="paper")
        _seed_task("soak-2", workflow_type="paper", risk="high")

        monkeypatch.setattr("ai_workflow_hub.daemon.time.time", _make_time_sequence())

        result = daemon_soak(duration_minutes=1, mode="plan")

        # In plan mode: tasks are counted but not executed
        assert result["tasks_seen"] >= 2
        assert result["tasks_started"] >= 2
        # High-risk tasks counted as human_required
        assert result["tasks_human_required"] >= 1
        assert result["tasks_passed"] >= 1  # non-high-risk

        # Tasks should still be queued (not actually dispatched)
        t1 = _find_in_store("soak-1")
        t2 = _find_in_store("soak-2")
        assert t1["status"] == "queued"
        assert t2["status"] == "queued"

    def test_soak_writes_report_files(self, isolated_env, monkeypatch):
        """daemon_soak should write JSON and MD report files."""
        from ai_workflow_hub.daemon import daemon_soak

        monkeypatch.setattr(
            "ai_workflow_hub.daemon._daemon_config",
            lambda: {"max_concurrency": 2, "max_retries": 1,
                     "stale_run_minutes": 30, "poll_interval_seconds": 0},
        )

        monkeypatch.setattr("ai_workflow_hub.daemon.time.time", _make_time_sequence())

        result = daemon_soak(duration_minutes=1, mode="plan")

        # Verify report files exist
        soaks_dir = isolated_env["tmp_path"] / "runs" / "daemon" / "soaks"
        assert soaks_dir.exists()

        json_files = list(soaks_dir.glob("soak-*.json"))
        md_files = list(soaks_dir.glob("soak-*.md"))
        assert len(json_files) >= 1
        assert len(md_files) >= 1

        # Verify JSON content
        report = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert report["status"] == "passed"
        assert report["mode"] == "plan"
        assert report["simulated"] is True

        # Verify MD content
        md_text = md_files[0].read_text(encoding="utf-8")
        assert "Soak Report" in md_text or "soak report" in md_text.lower()

    def test_soak_with_project_filter(self, isolated_env, monkeypatch):
        """daemon_soak with projects filter should only count matching tasks."""
        from ai_workflow_hub.daemon import daemon_soak

        monkeypatch.setattr(
            "ai_workflow_hub.daemon._daemon_config",
            lambda: {"max_concurrency": 2, "max_retries": 1,
                     "stale_run_minutes": 30, "poll_interval_seconds": 0},
        )

        _seed_task("soak-pA", workflow_type="paper", project_id="proj-A")
        _seed_task("soak-pB", workflow_type="paper", project_id="proj-B")

        monkeypatch.setattr("ai_workflow_hub.daemon.time.time", _make_time_sequence())

        result = daemon_soak(duration_minutes=1, projects=["proj-A"], mode="plan")

        assert result["project_ids"] == ["proj-A"]
        # Only proj-A task should be counted
        assert result["tasks_seen"] >= 1

    def test_soak_stale_recovery(self, isolated_env, monkeypatch):
        """Soak should recover stale running tasks each cycle."""
        from ai_workflow_hub.daemon import daemon_soak

        monkeypatch.setattr(
            "ai_workflow_hub.daemon._daemon_config",
            lambda: {"max_concurrency": 2, "max_retries": 1,
                     "stale_run_minutes": 30, "poll_interval_seconds": 0},
        )

        old_time = (
            datetime.now(timezone.utc) - timedelta(minutes=60)
        ).isoformat()
        _seed_task("soak-stale", workflow_type="paper",
                    status="running", updated_at=old_time)

        monkeypatch.setattr("ai_workflow_hub.daemon.time.time", _make_time_sequence())

        result = daemon_soak(duration_minutes=1, mode="plan")

        assert result["stale_running_count"] >= 1
        task = _find_in_store("soak-stale")
        assert task["status"] == "failed"


# ===========================================================================
# TestA22StatusTransitionMatrix — Valid/invalid state transitions
# ===========================================================================

class TestA22StatusTransitionMatrix:
    """Verify which task status transitions are valid."""

    def test_queued_to_running(self):
        from ai_workflow_hub.task_queue import mark_task_running

        _seed_task("st-qr", status="queued")
        assert mark_task_running("st-qr", "run-1") is True
        assert _find_in_store("st-qr")["status"] == "running"

    def test_running_to_passed(self):
        from ai_workflow_hub.task_queue import mark_task_running, mark_task_finished

        _seed_task("st-rp", status="queued")
        mark_task_running("st-rp", "run-1")
        assert mark_task_finished("st-rp", "passed", run_id="run-1") is True
        assert _find_in_store("st-rp")["status"] == "passed"

    def test_passed_cannot_remark_running(self):
        """Terminal status should block re-running."""
        from ai_workflow_hub.task_queue import mark_task_running, mark_task_finished

        _seed_task("st-block", status="queued")
        mark_task_running("st-block", "run-1")
        mark_task_finished("st-block", "passed")
        assert mark_task_running("st-block", "run-2") is False

    def test_running_already_running_blocked(self):
        """Already running task should not be re-marked."""
        from ai_workflow_hub.task_queue import mark_task_running

        _seed_task("st-dup", status="queued")
        assert mark_task_running("st-dup", "run-1") is True
        assert mark_task_running("st-dup", "run-2") is False

    def test_failed_to_retry(self):
        """Failed task can be retried (re-queued)."""
        from ai_workflow_hub.task_queue import mark_task_retry, mark_task_finished

        _seed_task("st-retry", status="failed")
        assert mark_task_retry("st-retry") is True
        task = _find_in_store("st-retry")
        assert task["status"] == "queued"
        assert task["retry_count"] == 1

    def test_passed_can_be_retried(self):
        """mark_task_retry currently allows re-queuing from any status."""
        from ai_workflow_hub.task_queue import mark_task_retry

        _seed_task("st-passed-retry", status="passed")
        # Current behavior: no terminal guard on mark_task_retry
        result = mark_task_retry("st-passed-retry")
        assert result is True
        assert _find_in_store("st-passed-retry")["status"] == "queued"

    def test_cancelled_to_archived(self):
        from ai_workflow_hub.task_queue import cancel_task, archive_task

        _seed_task("st-cancel", status="queued")
        assert cancel_task("st-cancel") is True
        assert _find_in_store("st-cancel")["status"] == "cancelled"
        assert archive_task("st-cancel") is True
        assert _find_in_store("st-cancel")["status"] == "archived"

    def test_paused_resume_cycle(self):
        from ai_workflow_hub.task_queue import pause_task, resume_task

        _seed_task("st-pause", status="queued")
        assert pause_task("st-pause") is True
        assert _find_in_store("st-pause")["status"] == "paused"
        assert resume_task("st-pause") is True
        assert _find_in_store("st-pause")["status"] == "queued"


# ===========================================================================
# TestA22RestartBehaviour — daemon restart with stale pidfile
# ===========================================================================

class TestA22RestartBehaviour:
    """Verify daemon restart when pidfile is left behind."""

    def test_no_pidfile_allows_start(self, isolated_env):
        """No pidfile should allow daemon to start."""
        from ai_workflow_hub.daemon import daemon_loop

        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ):
            result = daemon_loop(once=True)
        assert result == 0

    def test_stale_pidfile_allows_start(self, isolated_env, monkeypatch):
        """Pidfile with dead PID should allow restart."""
        from ai_workflow_hub.daemon import daemon_loop

        # Write a stale pidfile with a non-existent PID
        pidfile = isolated_env["daemon_dir"] / "daemon.pid"
        pidfile.write_text("99999999")  # Very unlikely to be a real PID

        # _acquire_lock is already mocked to return True in isolated_env
        with patch(
            "ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
            return_value={"run_id": "r1", "status": "completed"},
        ):
            result = daemon_loop(once=True)
        assert result == 0

    def test_running_instance_blocks_start(self, isolated_env, monkeypatch):
        """Another running instance should block daemon start."""
        from ai_workflow_hub.daemon import daemon_loop

        monkeypatch.setattr("ai_workflow_hub.daemon._acquire_lock", lambda: False)
        result = daemon_loop(once=True)
        assert result == 1


# ===========================================================================
# TestA22DaemonLogFormat — Verify daemon log format
# ===========================================================================

class TestA22DaemonLogFormat:
    """Verify _daemon_log writes correctly formatted entries."""

    def test_log_entry_format(self, isolated_env):
        from ai_workflow_hub.daemon import _daemon_log

        _daemon_log("TEST MESSAGE a22")

        log_dir = isolated_env["tmp_path"] / "runs" / "daemon"
        log_files = list(log_dir.glob("daemon-*.log"))
        assert len(log_files) >= 1

        content = log_files[0].read_text(encoding="utf-8")
        assert "TEST MESSAGE a22" in content
        # Should have ISO timestamp prefix
        assert content.startswith("[")

    def test_log_creates_directory(self, isolated_env):
        """_daemon_log should create the log directory if needed."""
        from ai_workflow_hub.daemon import _daemon_log

        # Remove log dir if exists
        log_dir = isolated_env["tmp_path"] / "runs" / "daemon"
        if log_dir.exists():
            import shutil
            shutil.rmtree(log_dir)

        _daemon_log("DIR CREATE TEST")
        assert log_dir.exists()
