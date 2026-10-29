"""Test B3 bounded dry-run chain."""
import json, sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.b3_bounded_submit import preflight, parse_decision, run_chain


def test_preflight_pass(tmp_path: Path):
    (tmp_path / "test-rid.zip").write_text("zip")
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    ok, msg = preflight(tmp_path, "test-rid")
    assert ok, msg


def test_preflight_fail_missing_zip(tmp_path: Path):
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    ok, msg = preflight(tmp_path, "test-rid")
    assert not ok


def test_parse_accepted():
    reply = "YAML\nREVIEW_RUN_ID: test-rid\noverall_judgment: accepted\nrest of reply " + "x" * 100
    d = parse_decision(reply, "test-rid")
    assert d["status"] == "accepted"
    assert d["review_run_id_match"] is True


def test_parse_blocked():
    reply = "YAML\nREVIEW_RUN_ID: test-rid\noverall_judgment: blocked\nrest " + "y" * 100
    d = parse_decision(reply, "test-rid")
    assert d["status"] == "blocked"


def test_short_reply_rejected():
    d = parse_decision("short", "test-rid")
    assert d["status"] == "review_unverified"


def test_rid_mismatch_rejected():
    reply = "REVIEW_RUN_ID: wrong-rid\noverall_judgment: accepted\n" + "z" * 100
    d = parse_decision(reply, "test-rid")
    assert d["status"] == "review_unverified"


def test_mock_chain_completes(tmp_path: Path, monkeypatch):
    """Run chain with mock reply — should complete all steps."""
    import tools.b3_bounded_submit as b3
    (tmp_path / "test-rid.zip").write_text("zip")
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    out = tmp_path / "b3-out"
    monkeypatch.setattr(b3, "OUTPUT_DIR", out)
    monkeypatch.setattr(b3, "ROOT", tmp_path)
    # Pre-create ledger
    (tmp_path / "DECISION_LEDGER.jsonl").write_text("", encoding="utf-8")
    reply = "YAML\nREVIEW_RUN_ID: test-rid\noverall_judgment: accepted\n" + "w" * 100
    result = b3.run_chain(tmp_path, "test-rid", reply_text=reply)
    assert result["status"] == "complete", f"Got: {result['status']}"
    assert len(result["steps"]) == 7
    assert result["decision"]["status"] == "accepted"


def test_route_written_has_blocked_items(tmp_path: Path, monkeypatch):
    """B3's POST_REVIEW_ROUTE must preserve all blocked items."""
    import tools.b3_bounded_submit as b3
    (tmp_path / "test-rid.zip").write_text("zip")
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    out = tmp_path / "b3-out"
    monkeypatch.setattr(b3, "OUTPUT_DIR", out)
    monkeypatch.setattr(b3, "ROOT", tmp_path)
    (tmp_path / "DECISION_LEDGER.jsonl").write_text("", encoding="utf-8")
    reply = "YAML\nREVIEW_RUN_ID: test-rid\noverall_judgment: blocked\n" + "v" * 100
    b3.run_chain(tmp_path, "test-rid", reply_text=reply)
    route = json.loads((out / "POST_REVIEW_ROUTE.json").read_text(encoding="utf-8"))
    assert route["overall_judgment"] == "blocked"
    for k in ["broader_real_chain_testing_unblocked", "production_promotion_approved",
              "hardcoded_driver_replacement_approved", "guard_removal_approved", "evidence_cleanup_approved"]:
        assert route[k] is False, f"{k} should be False"


def test_ledger_appended(tmp_path: Path, monkeypatch):
    """B3 must append to DECISION_LEDGER."""
    import tools.b3_bounded_submit as b3
    (tmp_path / "test-rid.zip").write_text("zip")
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    out = tmp_path / "b3-out"
    monkeypatch.setattr(b3, "OUTPUT_DIR", out)
    monkeypatch.setattr(b3, "ROOT", tmp_path)
    ledger = tmp_path / "DECISION_LEDGER.jsonl"
    ledger.write_text("", encoding="utf-8")
    reply = "YAML\nREVIEW_RUN_ID: test-rid\noverall_judgment: accepted\n" + "u" * 100
    b3.run_chain(tmp_path, "test-rid", reply_text=reply)
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["judgment"] == "accepted"
    assert entry["decision"] == "b3_bounded_dryrun"


def test_run_chain_short_reply_stops_no_route(tmp_path: Path, monkeypatch):
    """Short reply → review_unverified → stop, no route/ledger written."""
    import tools.b3_bounded_submit as b3
    (tmp_path / "test-rid.zip").write_text("zip")
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    out = tmp_path / "b3-out"
    monkeypatch.setattr(b3, "OUTPUT_DIR", out)
    monkeypatch.setattr(b3, "ROOT", tmp_path)
    (tmp_path / "DECISION_LEDGER.jsonl").write_text("", encoding="utf-8")
    result = b3.run_chain(tmp_path, "test-rid", reply_text="too short")
    assert result["status"] == "stopped_review_unverified"
    assert not (out / "POST_REVIEW_ROUTE.json").exists(), "route should NOT be written on fail"


def test_run_chain_rid_mismatch_stops_no_ledger(tmp_path: Path, monkeypatch):
    """RID mismatch → review_unverified → stop, no ledger append."""
    import tools.b3_bounded_submit as b3
    (tmp_path / "test-rid.zip").write_text("zip")
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    out = tmp_path / "b3-out"
    monkeypatch.setattr(b3, "OUTPUT_DIR", out)
    monkeypatch.setattr(b3, "ROOT", tmp_path)
    ledger = tmp_path / "DECISION_LEDGER.jsonl"
    ledger.write_text("", encoding="utf-8")
    reply = "REVIEW_RUN_ID: wrong-rid\noverall_judgment: accepted\n" + "x" * 100
    result = b3.run_chain(tmp_path, "test-rid", reply_text=reply)
    assert result["status"] == "stopped_review_unverified"
    assert ledger.read_text(encoding="utf-8").strip() == "", "ledger should be empty"


def test_run_chain_template_echo_stops(tmp_path: Path, monkeypatch):
    """Template echo → review_unverified → stop."""
    import tools.b3_bounded_submit as b3
    (tmp_path / "test-rid.zip").write_text("zip")
    (tmp_path / "GPT_REVIEW_PROMPT.md").write_text("prompt")
    out = tmp_path / "b3-out"
    monkeypatch.setattr(b3, "OUTPUT_DIR", out)
    monkeypatch.setattr(b3, "ROOT", tmp_path)
    (tmp_path / "DECISION_LEDGER.jsonl").write_text("", encoding="utf-8")
    reply = "授权请求 模板回声 REVIEW_RUN_ID: test-rid\noverall_judgment: accepted\n" + "y" * 100
    result = b3.run_chain(tmp_path, "test-rid", reply_text=reply)
    assert result["status"] == "stopped_review_unverified"
