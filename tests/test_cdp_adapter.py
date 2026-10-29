import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from control_plane.cdp_adapter import CdpAdapter, AdapterMode, create_adapter
from control_plane.submission_result import SubmissionRequest


def test_dry_run_mode_submits_successfully():
    adapter = create_adapter("dry_run")
    req = SubmissionRequest(review_run_id="test")
    result = adapter.submit(req)
    assert result.success is True
    assert result.mode == "dry_run"


def test_not_configured_returns_failure():
    adapter = create_adapter("not_configured")
    req = SubmissionRequest(review_run_id="test")
    result = adapter.submit(req)
    assert result.success is False
    assert result.mode == "not_configured"


def test_unavailable_returns_failure():
    adapter = create_adapter("unavailable")
    req = SubmissionRequest(review_run_id="test")
    result = adapter.submit(req)
    assert result.success is False
    assert result.mode == "unavailable"


def test_health_check_in_dry_run():
    adapter = create_adapter("dry_run")
    assert adapter.health_check() is True


def test_can_submit_in_dry_run():
    adapter = create_adapter("dry_run")
    assert adapter.can_submit() is True


def test_safety_attestation():
    adapter = create_adapter("dry_run")
    attest = adapter.safety_attestation()
    assert attest["no_real_cdp"] is True
    assert attest["no_playwright"] is True
    assert attest["no_gpt_submission"] is True


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        create_adapter("invalid_mode")
