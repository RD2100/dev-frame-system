import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from control_plane.submission_result import (
    SubmissionRequest, SubmissionResult, dry_run_result
)
from control_plane.submission_adapter import SubmissionAdapter, create_adapter


def test_dry_run_result_returns_success():
    req = SubmissionRequest(review_run_id="test-rid", zip_path="/tmp/test.zip")
    result = dry_run_result(req)
    assert result.success is True
    assert result.review_run_id == "test-rid"
    assert result.mode == "dry_run"
    assert result.captured_reply_sha256 == "dry_run_no_capture"


def test_adapter_creates_in_dry_run_mode():
    adapter = create_adapter()
    assert adapter.mode == "dry_run"
    assert adapter.can_submit() is True


def test_adapter_submit_returns_dry_run_result():
    adapter = create_adapter()
    req = SubmissionRequest(review_run_id="g3-test", zip_path="/tmp/test.zip")
    result = adapter.submit(req)
    assert result.success is True
    assert result.mode == "dry_run"
    assert "g3-test" in result.detail


def test_adapter_rejects_non_dry_run_mode():
    with pytest.raises(ValueError):
        SubmissionAdapter(mode="live")


def test_submission_request_defaults():
    req = SubmissionRequest()
    assert req.zip_path == ""
    assert req.prompt_text == ""
    assert req.conversation_id == ""


def test_submission_result_defaults():
    result = SubmissionResult()
    assert result.success is False
    assert result.parsed_judgment == "pending"
    assert result.mode == "dry_run"
