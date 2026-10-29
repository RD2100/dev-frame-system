"""Test B1 multi-pack replay scanner."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.b1_replay import classify, scan_packs, generate_output


def test_classify_accepted():
    assert classify("accepted") == "accepted"

def test_classify_blocked():
    assert classify("blocked") == "blocked"
    assert classify("BLOCKED") == "blocked"

def test_classify_human_required():
    assert classify("human_required") == "human_required"

def test_classify_unknown():
    assert classify("garbage") == "unknown"
    assert classify("pending") == "unknown"

def test_classify_needs_more_evidence():
    assert classify("needs_more_evidence") == "needs_more_evidence"

def test_scan_mock_pack(tmp_path: Path, monkeypatch):
    """scan_packs should detect packs with POST_REVIEW_ROUTE.json."""
    import tools.b1_replay as b1
    d = tmp_path / "test-pack"
    d.mkdir()
    (d / "POST_REVIEW_ROUTE.json").write_text(json.dumps({
        "review_run_id": "test-rid", "overall_judgment": "accepted",
        "broader_real_chain_testing_unblocked": False,
        "production_promotion_approved": False,
        "hardcoded_driver_replacement_approved": False,
        "guard_removal_approved": False,
        "evidence_cleanup_approved": False,
    }), encoding="utf-8")
    # Create mock artifacts
    (d / "SAFETY_CHECK.md").write_text("x")
    (d / "PACK_MANIFEST.md").write_text("x")
    (d / "VALIDATION_RESULT.json").write_text(json.dumps({"validation_verdict": "passed"}))
    monkeypatch.setattr(b1, "SCAN_ROOT", tmp_path)
    monkeypatch.setattr(b1, "ROOT", tmp_path)  # fix relative_to
    packs = b1.scan_packs()
    assert len(packs) == 1
    assert packs[0]["category"] == "accepted"
    assert packs[0]["checks"]["blocked_items_preserved"] == "pass"

def test_generate_output_counts_correctly():
    packs = [
        {"path": "a", "review_run_id": "r1", "category": "accepted",
         "checks": {"blocked_items_preserved": "pass"}, "errors": []},
        {"path": "b", "review_run_id": "r2", "category": "blocked",
         "checks": {"blocked_items_preserved": "pass"}, "errors": ["missing"]},
    ]
    data = generate_output(packs)
    assert data["total_packs_scanned"] == 2
    assert data["by_category"]["accepted"] == 1
    assert data["by_category"]["blocked"] == 1
    assert data["summary"]["pass_count"] == 2

def test_blocked_item_violation_detected(tmp_path: Path, monkeypatch):
    """Pack with blocked item = true should be caught."""
    import tools.b1_replay as b1
    d = tmp_path / "bad-pack"
    d.mkdir()
    (d / "POST_REVIEW_ROUTE.json").write_text(json.dumps({
        "review_run_id": "bad", "overall_judgment": "accepted",
        "broader_real_chain_testing_unblocked": True,  # VIOLATION
        "production_promotion_approved": False,
        "hardcoded_driver_replacement_approved": False,
        "guard_removal_approved": False,
        "evidence_cleanup_approved": False,
    }), encoding="utf-8")
    monkeypatch.setattr(b1, "SCAN_ROOT", tmp_path)
    monkeypatch.setattr(b1, "ROOT", tmp_path)  # fix relative_to
    packs = b1.scan_packs()
    assert packs[0]["checks"]["blocked_items_preserved"] == "fail"
