from pathlib import Path


def test_batch_attempt_owner_and_revision_reject_stale_overwrite(tmp_path, monkeypatch):
    from ai_workflow_hub import goal_store

    monkeypatch.setattr(goal_store, "GOALS_DIR", Path(tmp_path))
    goal = goal_store.create_goal("attempt ownership")
    batch = goal_store.add_batch(goal["goal_id"], "tests", "ownership")

    assert goal_store.update_batch_status(goal["goal_id"], batch["batch_id"], "running", run_id="attempt-a", expected_revision=0)
    state = goal_store.get_batch(goal["goal_id"], batch["batch_id"])
    assert state["attempt_id"] == "attempt-a"
    assert state["revision"] == 1
    assert not goal_store.update_batch_status(goal["goal_id"], batch["batch_id"], "passed", run_id="attempt-b", expected_revision=1)
    assert not goal_store.update_batch_status(goal["goal_id"], batch["batch_id"], "passed", run_id="attempt-a", expected_revision=0)
    assert goal_store.get_batch(goal["goal_id"], batch["batch_id"])["status"] == "running"
