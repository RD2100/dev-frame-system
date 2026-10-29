"""Test CDP Handoff Skill Deprecation & Active-Pack Cleanup v1.

Validates:
  - Handoff-only is not treated as submitted
  - pyperclip is not allowed for formal review
  - CDP handoff is deprecated
  - not_submitted requires NOT_AVAILABLE
  - review_unverified cannot be accepted
  - Active pack is handoff-free
  - CDP submission status required for submitted state
  - REVIEW_RUN_ID required for verified review
  - Evidence gate fails on handoff-only submitted
  - No historical evidence deleted
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "_reports" / "gca-phase3" / "cdp-handoff-deprecation"
PACK_DIR = ROOT / "_reports" / "gca-phase3" / "control-plane-responsibility-consolidation"
HANDOFF_DIR = ROOT / "_reports" / "browser-cdp-handoff"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Test 1: handoff-only not submitted ──

def test_handoff_only_not_submitted():
    """Handoff-only must not be treated as submitted."""
    # Check CDP_HANDOFF.md exists but is deprecated, not active flow
    handoff_md = HANDOFF_DIR / "CDP_HANDOFF.md"
    if handoff_md.exists():
        text = read_text(handoff_md)
        # Verify it contains handoff instructions, not submission confirmation
        assert "Manual Steps" in text or "handoff" in text.lower(), \
            "CDP_HANDOFF.md is a handoff doc, not a submission receipt"
    # The deprecation notice must explicitly forbid handoff-only as submitted
    dep_path = REPORT_DIR / "CDP_HANDOFF_DEPRECATION_NOTICE.md"
    assert dep_path.exists(), "Deprecation notice must exist"
    dep_text = read_text(dep_path)
    assert "handoff_only_counts_as_submitted: false" in dep_text.lower(), \
        "Must declare handoff_only does not count as submitted"


# ── Test 2: pyperclip not allowed ──

def test_pyperclip_not_allowed_for_formal_review():
    """pyperclip clipboard writes must not be used as formal review evidence."""
    dep_path = REPORT_DIR / "CDP_HANDOFF_DEPRECATION_NOTICE.md"
    dep_text = read_text(dep_path)
    assert "pyperclip_allowed: false" in dep_text.lower(), \
        "Must prohibit pyperclip"


# ── Test 3: CDP handoff deprecated ──

def test_cdp_handoff_deprecated():
    """CDP handoff skill must be marked deprecated."""
    dep_path = REPORT_DIR / "CDP_HANDOFF_DEPRECATION_NOTICE.md"
    dep_text = read_text(dep_path)
    assert "handoff_skill_status: deprecated" in dep_text.lower(), \
        "Must mark handoff skill as deprecated"
    assert "browser_cdp_handoff_allowed: false" in dep_text.lower(), \
        "Must disallow browser CDP handoff"


# ── Test 4: not_submitted requires NOT_AVAILABLE ──

def test_not_submitted_requires_not_available_result():
    """When not submitted, GPT_REVIEW_RESULT must be NOT_AVAILABLE."""
    gr_path = PACK_DIR / "GPT_REVIEW_RESULT.md"
    assert gr_path.exists(), "Active pack GPT_REVIEW_RESULT.md must exist"
    gr_text = read_text(gr_path)
    assert "NOT_AVAILABLE" in gr_text, \
        "not_submitted state requires GPT_REVIEW_RESULT = NOT_AVAILABLE"
    # Also check GPT_REVIEW_DECISION
    gd_path = PACK_DIR / "GPT_REVIEW_DECISION.md"
    assert gd_path.exists(), "Active pack GPT_REVIEW_DECISION.md must exist"
    gd_text = read_text(gd_path)
    assert "NOT_AVAILABLE" in gd_text, \
        "not_submitted state requires GPT_REVIEW_DECISION = NOT_AVAILABLE"


# ── Test 5: review_unverified cannot be accepted ──

def test_review_unverified_cannot_be_accepted():
    """review_unverified state must not be treated as accepted."""
    # Check policy document
    pol_path = REPORT_DIR / "CDP_SUBMISSION_POLICY_UPDATE.md"
    pol_text = read_text(pol_path)
    assert "decision_must_not_be_accepted: true" in pol_text.lower(), \
        "Policy must forbid accepted on review_unverified"


# ── Test 6: active pack handoff-free ──

def test_handoff_artifact_excluded_from_active_pack():
    """Active pack must not contain handoff artifacts."""
    import zipfile
    pack_zip = PACK_DIR / "control-plane-responsibility-consolidation-v1-pack.zip"
    if pack_zip.exists():
        with zipfile.ZipFile(pack_zip, 'r') as zf:
            names = zf.namelist()
            handoff_files = [n for n in names if 'handoff' in n.lower() or 'cdp_handoff' in n.lower()]
            assert len(handoff_files) == 0, \
                f"Active pack must not contain handoff files: {handoff_files}"


# ── Test 7: CDP status required for submitted ──

def test_cdp_status_required_for_submitted():
    """Policy must require CDP_SUBMISSION_STATUS.json for submitted state."""
    pol_path = REPORT_DIR / "CDP_SUBMISSION_POLICY_UPDATE.md"
    pol_text = read_text(pol_path)
    assert "CDP_SUBMISSION_STATUS.json" in pol_text, \
        "Policy must reference CDP_SUBMISSION_STATUS.json"


# ── Test 8: REVIEW_RUN_ID required for verified ──

def test_review_run_id_required_for_verified_review():
    """Verified review must require REVIEW_RUN_ID."""
    pol_path = REPORT_DIR / "CDP_SUBMISSION_POLICY_UPDATE.md"
    pol_text = read_text(pol_path)
    assert "review_run_id" in pol_text.lower(), \
        "Policy must reference REVIEW_RUN_ID verification"


# ── Test 9: evidence gate fails on handoff-only submitted ──

def test_evidence_gate_fails_on_handoff_only_submitted():
    """Evidence Integrity Gate must reject handoff-only as submitted."""
    ei_path = REPORT_DIR / "EVIDENCE_INTEGRITY_RESULT.json"
    if ei_path.exists():
        ei = json.loads(read_text(ei_path))
        assert ei.get("handoff_only_counts_as_submitted") == False, \
            "Evidence gate must reject handoff-only as submitted"


# ── Test 10: no historical evidence deleted ──

def test_no_historical_evidence_deleted():
    """Historical handoff artifacts must be preserved."""
    # Check that handoff directory still exists
    assert HANDOFF_DIR.exists(), \
        "Historical handoff directory must be preserved"
    # Check that CDP_HANDOFF.md still exists
    handoff_md = HANDOFF_DIR / "CDP_HANDOFF.md"
    assert handoff_md.exists(), \
        "CDP_HANDOFF.md must be preserved as historical evidence"
    # Check that oracle_chatgpt_cdp_handoff.py still exists
    handoff_script = ROOT / "tools" / "oracle_chatgpt_cdp_handoff.py"
    assert handoff_script.exists(), \
        "oracle_chatgpt_cdp_handoff.py must be preserved (not deleted)"


# ── Additional: deprecation files exist ──

def test_deprecation_notice_exists():
    assert (REPORT_DIR / "CDP_HANDOFF_DEPRECATION_NOTICE.md").exists()


def test_artifact_inventory_exists():
    assert (REPORT_DIR / "HANDOFF_ARTIFACT_INVENTORY.md").exists()


def test_active_pack_cleanup_report_exists():
    assert (REPORT_DIR / "ACTIVE_PACK_CLEANUP_REPORT.md").exists()


def test_cdp_submission_policy_update_exists():
    assert (REPORT_DIR / "CDP_SUBMISSION_POLICY_UPDATE.md").exists()
