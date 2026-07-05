"""Tests for Phase 1C: rdreview prepare-only skeleton."""
from __future__ import annotations

import json

from control_plane.rdreview import generate_review_packet, cmd_rdreview_prepare
from control_plane.review_governance_validator import validate_packet, derive_projection


# ---------------------------------------------------------------------------
# generate_review_packet
# ---------------------------------------------------------------------------

def test_generate_review_packet_has_required_top_level_keys():
    packet = generate_review_packet("wi-review-1", "Test review intent")
    for key in ("schema_version", "project", "work_item", "runs", "artifacts",
                "evidence", "decisions", "principals", "projection"):
        assert key in packet, f"missing key: {key}"


def test_generate_review_packet_work_item_kind_is_review():
    packet = generate_review_packet("wi-review-1", "Test intent")
    assert packet["work_item"]["kind"] == "review"


def test_generate_review_packet_status_is_ready():
    packet = generate_review_packet("wi-review-1", "Test intent")
    assert packet["work_item"]["status"] == "ready"


def test_generate_review_packet_no_decisions_or_evidence():
    packet = generate_review_packet("wi-review-1", "Test intent")
    assert packet["decisions"] == []
    assert packet["evidence"] == []


def test_generate_review_packet_validates_schema():
    packet = generate_review_packet("wi-review-1", "Test intent")
    result = validate_packet(packet)
    assert result.valid, "\n".join(result.errors)


def test_generate_review_packet_projection_ready():
    packet = generate_review_packet("wi-review-1", "Test intent")
    assert packet["projection"]["computed_status"] == "ready"


def test_generate_review_packet_deterministic_ids():
    p1 = generate_review_packet("wi-review-1", "Intent A")
    p2 = generate_review_packet("wi-review-1", "Intent B")
    assert p1["work_item"]["id"] == p2["work_item"]["id"]
    assert p1["runs"][0]["id"] == p2["runs"][0]["id"]
    assert p1["artifacts"][0]["id"] == p2["artifacts"][0]["id"]


def test_generate_review_packet_different_work_items_different_ids():
    p1 = generate_review_packet("wi-review-1", "Intent A")
    p2 = generate_review_packet("wi-review-2", "Intent B")
    assert p1["work_item"]["id"] != p2["work_item"]["id"]
    assert p1["runs"][0]["id"] != p2["runs"][0]["id"]


def test_generate_review_packet_projection_matches_derive():
    packet = generate_review_packet("wi-review-1", "Test intent")
    derived = derive_projection(packet)
    assert packet["projection"]["computed_status"] == derived["computed_status"]
    assert packet["projection"]["blocked_reason"] == derived["blocked_reason"]
    assert packet["projection"]["evidence_summary"] == derived["evidence_summary"]
    assert packet["projection"]["decision_summary"] == derived["decision_summary"]
    assert packet["projection"]["allowed_actions"] == derived["allowed_actions"]


def test_generate_review_packet_no_runtime_side_effects(tmp_path, capsys):
    """Verify cmd_rdreview_prepare only writes to file or stdout, no state changes."""
    output_file = tmp_path / "packet.json"
    rc = cmd_rdreview_prepare("wi-review-1", "Test intent", str(output_file))
    assert rc == 0
    assert output_file.exists()
    packet = json.loads(output_file.read_text(encoding="utf-8"))
    assert packet["work_item"]["status"] == "ready"
    captured = capsys.readouterr()
    assert "Review packet written to" in captured.out
