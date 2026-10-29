"""Test CDP timeout recovery and watchdog behavior."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "_reports" / "gca-phase3" / "cdp-submission-timeout-recovery"
CDP_FLOW = ROOT / "tools" / "oracle_gpt_full_review_flow.py"


def test_cdp_submission_timeout_writes_status():
    """CDP timeout must produce CDP_SUBMISSION_STATUS.json with submitted=false."""
    status_path = D / "CDP_SUBMISSION_STATUS.json"
    assert status_path.exists(), "CDP_SUBMISSION_STATUS.json must exist"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["submitted"] == False, "Must not be submitted"
    assert status["status"] == "timeout", "Status must be timeout"


def test_cdp_timeout_does_not_write_accepted():
    """Timeout must not write accepted/partial/blocked to review files."""
    for fname in ["GPT_REVIEW_RESULT.md", "GPT_REVIEW_DECISION.md"]:
        path = D / fname
        assert path.exists(), f"{fname} must exist"
        text = path.read_text(encoding="utf-8")
        assert "NOT_AVAILABLE" in text, f"{fname} must say NOT_AVAILABLE, got: {text[:50]}"
        assert "accepted" not in text.lower() or "not_available" in text.lower(), \
            f"{fname} must not claim accepted"


def test_short_gpt_capture_marked_unverified():
    """CDP flow must have watchdog for short captures (< 100 chars)."""
    # Verify watchdog exists in the source
    text = CDP_FLOW.read_text(encoding="utf-8")
    assert "MIN_REPLY_CHARS" in text, "Watchdog must check minimum reply length"
    assert "review_unverified" in text, "Short capture must be marked review_unverified"
    assert "NOT_AVAILABLE_DUE_TO_SHORT_CAPTURE" in text, "Must write NOT_AVAILABLE on short capture"


def test_missing_review_run_id_marked_unverified():
    """Capture without REVIEW_RUN_ID must be marked review_unverified."""
    text = CDP_FLOW.read_text(encoding="utf-8")
    assert "REVIEW_RUN_ID" in text, "Watchdog must check for REVIEW_RUN_ID"
    assert "no REVIEW_RUN_ID" in text.lower() or "missing_review_run_id" in text, \
        "Must detect missing REVIEW_RUN_ID"


def test_verified_review_requires_review_run_id():
    """Verified review must require REVIEW_RUN_ID in GPT reply."""
    text = CDP_FLOW.read_text(encoding="utf-8")
    assert "rid_match" in text, "Must extract REVIEW_RUN_ID from reply"
    assert "rid_match.group(1) != expected_rid" in text, \
        "Must reject REVIEW_RUN_ID mismatch, not just missing REVIEW_RUN_ID"
    assert "gpt_reply_review_run_id_mismatch" in text, \
        "Must record explicit REVIEW_RUN_ID mismatch reason"
    assert "watchdog_pass" in text, "Must have watchdog_pass log event"


def test_timeout_exit_code_nonzero():
    """Watchdog must exit non-zero on failure."""
    text = CDP_FLOW.read_text(encoding="utf-8")
    assert "sys.exit(20)" in text, "Watchdog failure must exit non-zero"


def test_no_handoff_on_cdp_timeout():
    """CDP timeout must not fall back to handoff."""
    status = json.loads((D / "CDP_SUBMISSION_STATUS.json").read_text(encoding="utf-8"))
    assert status.get("handoff_used") == False


def test_no_pyperclip_on_cdp_timeout():
    """CDP timeout must not use pyperclip."""
    status = json.loads((D / "CDP_SUBMISSION_STATUS.json").read_text(encoding="utf-8"))
    assert status.get("pyperclip_used") == False


# Additional policy checks
def test_evidence_gate_timeout_state():
    """Evidence gate must reflect timeout state."""
    ei = json.loads((D / "EVIDENCE_INTEGRITY_RESULT.json").read_text(encoding="utf-8"))
    assert ei["ready_for_review"] == False, "Not ready for review after timeout"
    assert ei["ready_for_retry"] == True, "Should be ready for retry"
    assert ei["submitted"] == False


def test_safety_check_clean():
    """Safety check must be clean."""
    sc = (D / "SAFETY_CHECK.md").read_text(encoding="utf-8")
    for check in ["files_deleted: no", "handoff_used: no", "pyperclip_used: no",
                  "computer_use_mcp_used: no", "production_promotion_executed: no"]:
        assert check in sc, f"Safety check must say: {check}"
