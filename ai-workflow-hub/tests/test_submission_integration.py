"""Test submission guard integration — gate + entrypoint + pilot."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.submission_guard import pre_submit_gate
from tools.submission_guard import record_submission_result
from tools.submission_guard import SUBMISSION_LOG


def test_gate_allows_first_submission(tmp_path: Path):
    """Gate should allow first submission."""
    assert pre_submit_gate(tmp_path, "test-rid-new") is True


def test_gate_blocks_cooldown(tmp_path: Path):
    """Gate should block re-submission within cooldown."""
    # Record a recent submission
    log_path = tmp_path / SUBMISSION_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({
        "review_run_id": "test-rid-cool", "action": "submit",
        "success": True, "timestamp": time.time(), "iso": "", "detail": ""
    }) + "\n", encoding="utf-8")
    try:
        pre_submit_gate(tmp_path, "test-rid-cool")
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 10


def test_gate_blocks_max_retries(tmp_path: Path):
    """Gate with 3 previous submits should block."""
    old_ts = time.time() - 120
    log_path = tmp_path / SUBMISSION_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"review_run_id": "test-max", "action": "submit",
                "success": False, "timestamp": old_ts, "iso": "", "detail": f"a{i}"}) + "\n")
    try:
        pre_submit_gate(tmp_path, "test-max")
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 10


def test_entrypoint_logs_success(tmp_path: Path):
    """Entrypoint should record successful submission."""
    result = record_submission_result(tmp_path, "test-log-ok", success=True, detail="test")
    assert result is True
    log_path = tmp_path / SUBMISSION_LOG
    assert log_path.exists()
    data = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert data["review_run_id"] == "test-log-ok"
    assert data["success"] is True


def test_entrypoint_logs_failure(tmp_path: Path):
    """Entrypoint should record failed submission."""
    result = record_submission_result(tmp_path, "test-log-fail", success=False)
    assert result is True
    log_path = tmp_path / SUBMISSION_LOG
    data = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert data["success"] is False


def test_entrypoint_handles_write_failure(tmp_path: Path, monkeypatch):
    """Entrypoint returns False on write failure — no crash."""
    def _failing_record(*args, **kwargs):
        raise OSError("Disk full")
    monkeypatch.setattr(
        "tools.submission_guard.record_submission", _failing_record
    )
    result = record_submission_result(tmp_path, "test-fail-write", success=True)
    assert result is False


def test_gate_different_rid_independent(tmp_path: Path):
    """Submitting with different RID should be allowed even if previous blocked."""
    # Block one RID
    log_path = tmp_path / SUBMISSION_LOG
    log_path.write_text(json.dumps({
        "review_run_id": "rid-blocked", "action": "submit",
        "success": False, "timestamp": time.time(), "iso": "", "detail": ""
    }) + "\n", encoding="utf-8")
    # Different RID should be allowed
    assert pre_submit_gate(tmp_path, "rid-different") is True


def test_log_write_failure_causes_exit(tmp_path: Path, monkeypatch):
    """Log write failure should return False (caller must sys.exit)."""
    def _fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(
        "tools.submission_guard.record_submission", _fail
    )
    result = record_submission_result(tmp_path, "test-exit", success=True)
    assert result is False, "Should return False on write failure — caller must sys.exit"


def test_gate_blocks_unwritable_log_dir(tmp_path: Path, monkeypatch):
    """Gate should block when log directory cannot be written."""
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    # Make pre_submit_gate fail by making the log path a directory (can't write file)
    log_path = read_only / "SUBMISSION_LOG.jsonl"
    log_path.mkdir()  # directory with same name blocks file creation
    try:
        pre_submit_gate(read_only, "test-ro")
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 10


def test_gate_allows_after_cooldown_expires(tmp_path: Path):
    """After cooldown period, re-submission should be allowed."""
    old_ts = time.time() - 120  # 120s ago, well past 30s cooldown
    log_path = tmp_path / SUBMISSION_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({
        "review_run_id": "test-expired", "action": "submit",
        "success": True, "timestamp": old_ts, "iso": "", "detail": ""
    }) + "\n", encoding="utf-8")
    # Should be allowed (cooldown expired)
    assert pre_submit_gate(tmp_path, "test-expired") is True


def test_failed_entrypoint_write_is_detectable(tmp_path: Path, monkeypatch):
    """Caller can detect entrypoint write failure via False return."""
    def _fail(*a, **kw):
        raise OSError("no space")
    monkeypatch.setattr("tools.submission_guard.record_submission", _fail)
    result = record_submission_result(tmp_path, "test-detect", success=True)
    assert result is False
    # Verify no log file was created (write failed cleanly)
    log_path = tmp_path / SUBMISSION_LOG
    assert not log_path.exists(), "Log should not exist after failed write"
