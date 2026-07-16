import json


def test_recover_run_evidence_prefers_actual_diff_over_worker_claim(tmp_path, monkeypatch):
    from ai_workflow_hub import goal_runner

    run_dir = tmp_path / "runs" / "demo" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({"changed_files": ["claimed.py"]}), encoding="utf-8")
    (run_dir / "diff.patch").write_text(
        "diff --git a/actual.py b/actual.py\n--- a/actual.py\n+++ b/actual.py\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(goal_runner, "_hub_dir", lambda: tmp_path)

    result = goal_runner.recover_run_evidence("demo", "run-1")

    assert result["source"] == "diff.patch"
    assert result["changed_files"] == ["actual.py"]
