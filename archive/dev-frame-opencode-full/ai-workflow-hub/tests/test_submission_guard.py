"""Test submission_guard — dedup and retry."""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.submission_guard import (
    check_before_submit, record_submission, get_submission_summary,
    SUBMISSION_LOG,
)


def test_first_submission_allowed(tmp_path: Path):
    ok, reason = check_before_submit(tmp_path, "test-rid-1")
    assert ok
    assert reason == "first_submission"


def test_submission_recorded(tmp_path: Path):
    record_submission(tmp_path, "test-rid-1", success=True)
    path = tmp_path / SUBMISSION_LOG
    assert path.exists()
    entries = [json.loads(line) for line in path.read_text().strip().splitlines()]
    assert len(entries) == 1
    assert entries[0]["review_run_id"] == "test-rid-1"
    assert entries[0]["success"] is True


def test_resubmit_within_limits_allowed(tmp_path: Path):
    record_submission(tmp_path, "test-rid-1")
    # Cooldown bypass for test: use past timestamp
    path = tmp_path / SUBMISSION_LOG
    # Overwrite with old timestamp
    old_entry = {
        "review_run_id": "test-rid-1", "action": "submit",
        "success": True, "timestamp": time.time() - 60,
        "iso": "", "detail": ""
    }
    path.write_text(json.dumps(old_entry) + "\n", encoding="utf-8")
    ok, reason = check_before_submit(tmp_path, "test-rid-1", cooldown_seconds=30)
    assert ok, f"Expected allowed, got: {reason}"
    assert "resubmit_allowed" in reason


def test_cooldown_blocks_resubmit(tmp_path: Path):
    record_submission(tmp_path, "test-rid-1")  # Just now
    ok, reason = check_before_submit(tmp_path, "test-rid-1", cooldown_seconds=30)
    assert not ok
    assert "cooldown" in reason


def test_max_resubmits_exceeded(tmp_path: Path):
    old_ts = time.time() - 120
    path = tmp_path / SUBMISSION_LOG
    for i in range(3):
        path.open("a", encoding="utf-8").write(
            json.dumps({"review_run_id": "test-rid-1", "action": "submit",
                        "success": False, "timestamp": old_ts, "iso": "", "detail": f"attempt_{i}"}) + "\n"
        )
    ok, reason = check_before_submit(tmp_path, "test-rid-1", max_resubmits=3, cooldown_seconds=30)
    assert not ok
    assert "max_resubmits" in reason


def test_different_rids_independent(tmp_path: Path):
    record_submission(tmp_path, "rid-a")
    ok, _ = check_before_submit(tmp_path, "rid-b")
    assert ok  # Different RID, should be first submission


def test_get_submission_summary(tmp_path: Path):
    record_submission(tmp_path, "rid-1", success=True)
    record_submission(tmp_path, "rid-1", success=False)
    record_submission(tmp_path, "rid-2", success=True)
    summary = get_submission_summary(tmp_path)
    assert summary["total_entries"] == 3
    assert summary["unique_rids"] == 2
    assert summary["by_review_run_id"]["rid-1"]["attempts"] == 2
    assert summary["by_review_run_id"]["rid-2"]["attempts"] == 1
