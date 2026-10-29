import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from control_plane.playwright_bridge import (
    BridgeMode, BridgeConfig, health_check, submit_via_bridge, safety_attestation,
)
from control_plane.submission_result import SubmissionRequest


def make_config(mode=BridgeMode.DISABLED, safety=False, conv=""):
    return BridgeConfig(mode=mode, safety_flag=safety, conversation_id=conv)


def test_disabled_mode_health_check_fails():
    ok, reason = health_check(make_config(BridgeMode.DISABLED))
    assert ok is False
    assert "disabled" in reason


def test_dry_run_health_check_passes():
    ok, reason = health_check(make_config(BridgeMode.DRY_RUN))
    assert ok is True


def test_live_without_safety_flag_blocked():
    ok, reason = health_check(make_config(BridgeMode.LIVE, safety=False, conv="id"))
    assert ok is False
    assert "safety_flag" in reason


def test_live_without_conversation_id_blocked():
    ok, reason = health_check(make_config(BridgeMode.LIVE, safety=True, conv=""))
    assert ok is False
    assert "conversation_id" in reason


def test_disabled_submit_returns_blocked():
    req = SubmissionRequest(review_run_id="test")
    result = submit_via_bridge(req, make_config(BridgeMode.DISABLED))
    assert result.success is False


def test_dry_run_submit_returns_success():
    req = SubmissionRequest(review_run_id="test")
    result = submit_via_bridge(req, make_config(BridgeMode.DRY_RUN))
    assert result.success is True
    assert result.mode == "dry_run"


def test_live_with_unreachable_cdp_returns_error():
    """Live mode with unreachable CDP should return a proper error, not placeholder."""
    req = SubmissionRequest(review_run_id="test")
    cfg = make_config(BridgeMode.LIVE)
    cfg.safety_flag = True
    cfg.conversation_id = "https://chatgpt.com/c/6a223019"
    cfg.cdp_port = 19999  # non-existent port
    result = submit_via_bridge(req, cfg)
    assert result.success is False
    assert result.mode == "live"
    assert "not yet implemented" not in result.detail.lower()


def test_live_missing_handoff_file_returns_error():
    """Live mode without HANDOFF.md should return file-not-found error."""
    req = SubmissionRequest(review_run_id="/nonexistent/NO_SUCH_FILE.md")
    cfg = make_config(BridgeMode.LIVE)
    cfg.safety_flag = True
    cfg.conversation_id = "https://chatgpt.com/c/test"
    cfg.cdp_port = 19999
    result = submit_via_bridge(req, cfg)
    # Should fail fast on missing file, not try CDP
    assert result.success is False


def test_live_without_playwright_returns_error():
    """Live mode without playwright installed should fail at health check."""
    cfg = make_config(BridgeMode.LIVE)
    cfg.safety_flag = True
    cfg.conversation_id = "6a223019"
    req = SubmissionRequest(review_run_id="HANDOFF.md")
    ok, reason = health_check(cfg)
    if "playwright_not_installed" in reason:
        # Expected when playwright is absent
        assert ok is False
    else:
        # playwright is installed, health check should pass
        assert ok is True


def test_safety_attestation_no_state_mutation():
    attest = safety_attestation(make_config(BridgeMode.DRY_RUN))
    assert attest["no_state_mutation"] is True
    assert attest["no_real_gpt_submit_in_tests"] is True
