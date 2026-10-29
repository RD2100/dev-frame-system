"""Test B2 multi-agent chain replay — 9 synthetic chain tests."""
import json, sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.b2_replay import classify_path, scan_chain, _extract_rid, _extract_judgment

def _write_route(d: Path, rid: str, judgment: str, blocked_ok=True):
    d.mkdir(parents=True, exist_ok=True)
    r = {"review_run_id": rid, "overall_judgment": judgment}
    if blocked_ok:
        r.update({"broader_real_chain_testing_unblocked": False, "production_promotion_approved": False,
                   "hardcoded_driver_replacement_approved": False, "guard_removal_approved": False,
                   "evidence_cleanup_approved": False})
    (d / "POST_REVIEW_ROUTE.json").write_text(json.dumps(r), encoding="utf-8")

def _write_decision(d: Path, rid: str, judgment: str):
    (d / "GPT_REVIEW_DECISION.md").write_text(f"REVIEW_RUN_ID: {rid}\noverall_judgment: {judgment}\n", encoding="utf-8")

def _write_result(d: Path, rid: str):
    (d / "GPT_REVIEW_RESULT.md").write_text(f"REVIEW_RUN_ID: {rid}\n", encoding="utf-8")

def test_extract_rid():
    assert _extract_rid("REVIEW_RUN_ID: test-123") == "test-123"
    assert _extract_rid("no rid here") == ""

def test_classify_paths():
    assert classify_path("accepted") == "accepted"
    assert classify_path("blocked") == "blocked"
    assert classify_path("rejected") == "rejected"
    assert classify_path("needs_more_evidence") == "needs_more_evidence"
    assert classify_path("review_unverified") == "review_unverified"

# ===== 9 synthetic chain tests =====

def test_accepted_complete_chain(tmp_path, monkeypatch):
    """Accepted pack with full chain: decision, result, route, ledger."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "acc", "rid-acc", "accepted")
    _write_decision(tmp_path / "acc", "rid-acc", "accepted")
    _write_result(tmp_path / "acc", "rid-acc")
    (tmp_path / "acc" / "GPT_REVIEW_PROMPT.md").write_text("REVIEW_RUN_ID: rid-acc", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({"rid-acc": "accepted"})
    assert packs[0]["classification"] not in ("actionable_fail",), f"Got {packs[0]['classification']}"

def test_blocked_stops_correctly(tmp_path, monkeypatch):
    """Blocked pack should NOT have execution artifacts."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "blk", "rid-blk", "blocked")
    _write_decision(tmp_path / "blk", "rid-blk", "blocked")
    (tmp_path / "blk" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-blk", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({"rid-blk": "blocked"})
    assert packs[0]["chain_status"] == "complete"

def test_needs_more_evidence_stops(tmp_path, monkeypatch):
    """needs_more_evidence pack should stop, no further chain."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "nme", "rid-nme", "needs_more_evidence")
    _write_decision(tmp_path / "nme", "rid-nme", "needs_more_evidence")
    (tmp_path / "nme" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-nme", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({})
    assert packs[0]["chain_status"] == "complete"

def test_rejected_stops(tmp_path, monkeypatch):
    """Rejected pack should stop."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "rej", "rid-rej", "rejected")
    _write_decision(tmp_path / "rej", "rid-rej", "rejected")
    (tmp_path / "rej" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-rej", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({})
    assert packs[0]["chain_status"] == "complete"

def test_review_unverified_stops(tmp_path, monkeypatch):
    """review_unverified pack should stop."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "ru", "rid-ru", "review_unverified")
    _write_decision(tmp_path / "ru", "rid-ru", "review_unverified")
    (tmp_path / "ru" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-ru", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({})
    assert packs[0]["chain_status"] == "complete"

def test_rid_mismatch_fail_closed(tmp_path, monkeypatch):
    """RID mismatch across sources → actionable_fail."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "mismatch", "rid-route", "accepted")
    _write_decision(tmp_path / "mismatch", "rid-decision", "accepted")
    (tmp_path / "mismatch" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-result", encoding="utf-8")
    (tmp_path / "mismatch" / "GPT_REVIEW_PROMPT.md").write_text("REVIEW_RUN_ID: rid-prompt", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({})
    assert packs[0]["checks"]["rid_match"] == "fail"
    assert packs[0]["classification"] == "actionable_fail"

def test_decision_route_mismatch(tmp_path, monkeypatch):
    """GPT decision says blocked, route says accepted → actionable_fail."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "conflict", "rid-conflict", "accepted")
    _write_decision(tmp_path / "conflict", "rid-conflict", "blocked")
    (tmp_path / "conflict" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-conflict", encoding="utf-8")
    (tmp_path / "conflict" / "GPT_REVIEW_PROMPT.md").write_text("REVIEW_RUN_ID: rid-conflict", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({})
    assert packs[0]["checks"]["route_decision_match"] == "fail"
    assert packs[0]["classification"] == "actionable_fail"

def test_blocked_with_exec_artifacts_chain_broken(tmp_path, monkeypatch):
    """Blocked pack that has execution artifacts → chain broken."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "blk-exec", "rid-blk-exec", "blocked")
    _write_decision(tmp_path / "blk-exec", "rid-blk-exec", "blocked")
    (tmp_path / "blk-exec" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-blk-exec", encoding="utf-8")
    (tmp_path / "blk-exec" / "UNIFIED_DIFF.patch").write_text("x")  # execution artifact!
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({"rid-blk-exec": "blocked"})
    assert packs[0]["chain_status"] == "broken"
    assert packs[0]["classification"] == "actionable_fail"

def test_accepted_no_closure_incomplete(tmp_path, monkeypatch):
    """Accepted pack missing closure → incomplete but not actionable."""
    import tools.b2_replay as b2
    _write_route(tmp_path / "acc-inc", "rid-acc-inc", "accepted")
    _write_decision(tmp_path / "acc-inc", "rid-acc-inc", "accepted")
    (tmp_path / "acc-inc" / "GPT_REVIEW_RESULT.md").write_text("REVIEW_RUN_ID: rid-acc-inc", encoding="utf-8")
    (tmp_path / "acc-inc" / "GPT_REVIEW_PROMPT.md").write_text("REVIEW_RUN_ID: rid-acc-inc", encoding="utf-8")
    monkeypatch.setattr(b2, "SCAN_ROOT", tmp_path); monkeypatch.setattr(b2, "ROOT", tmp_path)
    packs = b2.scan_chain({"rid-acc-inc": "accepted"})
    assert packs[0]["chain_status"] == "incomplete"
