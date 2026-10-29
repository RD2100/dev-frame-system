"""Quick debug for run_queued_tasks with mocked store."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from contextlib import contextmanager
from pathlib import Path
import tempfile
from unittest.mock import patch

tmp = tempfile.mkdtemp()
proj_path = Path(tmp) / "project"
proj_path.mkdir()

_store = {"tasks": []}

def _mg():
    return _store

def _ms(data):
    if data is not _store:
        _store.clear()
        _store.update(data)

@contextmanager
def _nl():
    yield

import ai_workflow_hub.task_queue as tq
import ai_workflow_hub.project_registry as pr
import ai_workflow_hub.daemon as daemon

tq.get_tasks = _mg
tq.save_tasks = _ms
tq.tasks_lock = _nl

daemon._daemon_config = lambda: {
    "max_concurrency": 2, "max_retries": 1,
    "stale_run_minutes": 30, "poll_interval_seconds": 1,
}

pr.find_project = lambda pid: {"id": pid, "enabled": True, "path": str(proj_path)}

_store["tasks"].append({
    "id": "test-1", "status": "queued", "project_id": "p1",
    "workflow_type": "paper", "dependencies": [], "retry_count": 0,
    "priority": "normal", "last_run_id": "", "last_started_at": "",
    "lease_until": "", "updated_at": "",
})

print("Tasks in store:", len(_store["tasks"]))
print("Task status:", _store["tasks"][0]["status"])

runnable = daemon.find_runnable_tasks()
print("Runnable tasks:", len(runnable))
for t in runnable:
    print("  -", t["id"], t["status"])

with patch("ai_workflow_hub.context_layer.adapters.paper_runtime.dispatch_paper_task",
           return_value={"run_id": "r1", "status": "completed"}) as mock_d:
    # Manually replicate run_queued_tasks logic with debug output
    cfg = daemon._daemon_config()
    max_concurrency = cfg.get("max_concurrency", 1)
    max_retries = cfg.get("max_retries", 1)
    runnable = daemon.find_runnable_tasks()
    print(f"cfg: max_concurrency={max_concurrency}, max_retries={max_retries}")
    print(f"runnable: {len(runnable)}")

    for t in runnable:
        print(f"  Processing {t['id']}:")
        rc = t.get("retry_count", 0)
        print(f"    retry_count={rc}, max_retries={max_retries}, rc > max_retries = {rc > max_retries}")
        if rc > max_retries:
            print("    SKIP: retry limit")
            continue

        project = pr.find_project(t["project_id"])
        print(f"    project={project}")
        if not project or not project.get("enabled", True):
            print("    SKIP: project disabled")
            continue

        pp = project.get("path", "")
        print(f"    proj_path={pp}, exists={Path(pp).exists()}")
        if not Path(pp).exists():
            print("    SKIP: path not found")
            continue

        run_id = f"daemon-{t['id']}"
        ok = tq.mark_task_running(t["id"], run_id)
        print(f"    mark_task_running({t['id']}, {run_id}) = {ok}")
        if not ok:
            print("    SKIP: mark_task_running failed")
            continue

        print("    EXECUTING")

    # Now try actual run_queued_tasks
    # Reset task status first
    _store["tasks"][0]["status"] = "queued"
    result = daemon.run_queued_tasks()
    print("run_queued_tasks result:", result)
    print("dispatch called:", mock_d.called)

print("Final task status:", _store["tasks"][0]["status"])
