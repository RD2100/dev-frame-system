"""Tests for Phase 1C: rdreview prepare-only skeleton."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema.validators import validator_for

from control_plane.cli.app import main as devframe_cli_main
from control_plane.rdreview import (
    cmd_rdreview_prepare,
    generate_review_packet,
    generate_review_prepare_bundle,
)
from control_plane.cli._review import cmd_rdreview
from control_plane.review_governance_validator import validate_packet, derive_projection

REPO_ROOT = Path(__file__).resolve().parents[3]


def _schema_validator(path: str):
    schema = json.loads((REPO_ROOT / path).read_text(encoding="utf-8-sig"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


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


def test_generate_review_prepare_bundle_contains_schema_valid_contracts():
    bundle = generate_review_prepare_bundle("wi-review-1", "Review Batch C prepare path")

    assert bundle["kind"] == "rdreview_prepare_bundle"
    assert validate_packet(bundle["review_packet"]).valid
    _schema_validator("schemas/runtime-governance/context-packet.schema.json").validate(
        bundle["context_packet"]
    )
    _schema_validator("schemas/runtime-governance/context-ledger.schema.json").validate(
        bundle["context_ledger"]
    )
    _schema_validator("schemas/runtime-governance/run-record.schema.json").validate(
        bundle["run_record"]
    )
    _schema_validator("schemas/agent-runtime/task-spec.schema.json").validate(
        bundle["task_spec"]
    )


def test_generate_review_prepare_bundle_is_prepare_only_not_acceptance():
    bundle = generate_review_prepare_bundle("wi-review-1", "Review Batch C prepare path")
    rendered = json.dumps(bundle, sort_keys=True)

    assert "final_ready" not in rendered
    assert "final_verdict_ref" not in bundle["run_record"]
    assert bundle["run_record"]["phase"] == "prepared"
    assert bundle["run_record"]["outcome"] == "unknown"
    assert bundle["run_record"]["review_state"] == "review_pending"
    assert bundle["run_record"]["gate_state"] == "not_evaluated"
    assert bundle["run_record"]["acceptance_state"] == "review_pending"
    assert bundle["run_record"]["review_refs"] == []
    assert bundle["run_record"]["gate_refs"] == []
    assert bundle["context_packet"]["constraints"]["authority_boundary"] == {
        "can_execute": False,
        "can_review": True,
        "can_claim_final_acceptance": False,
        "final_verdict_required": True,
    }


def test_generate_review_prepare_bundle_makes_missing_context_and_stop_lines_visible():
    bundle = generate_review_prepare_bundle("wi-review-1", "Review Batch C prepare path")

    omitted = bundle["evidence_inventory"]["omitted_required_refs"]
    assert {item["ref"] for item in omitted} == {
        "independent-review-record",
        "execution-or-test-evidence",
    }
    assert bundle["context_packet"]["completeness_state"] == "insufficient_evidence"
    stop_lines = " ".join(bundle["stop_lines"]).lower()
    for phrase in (
        "no automatic retrieval",
        "no browser submission",
        "no live external reviewer",
        "no runtime execution",
    ):
        assert phrase in stop_lines
    assert bundle["review_request"]["can_execute"] is False
    assert bundle["review_request"]["can_submit_externally"] is False
    assert bundle["review_request"]["can_claim_acceptance"] is False


def test_generate_review_prepare_bundle_inspect_and_resume_are_manual_only():
    bundle = generate_review_prepare_bundle("wi-review-1", "Review Batch C prepare path")

    assert bundle["inspect_output"]["mode"] == "read_only"
    assert bundle["inspect_output"]["review_state"] == "review_pending"
    assert bundle["inspect_output"]["missing_required_refs"] == [
        "independent-review-record",
        "execution-or-test-evidence",
    ]
    assert bundle["resume_output"]["mode"] == "manual_only"
    assert "browser or Web AI submission" in bundle["resume_output"]["blocked_actions"]


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


def test_cmd_rdreview_prepare_bundle_output(tmp_path, capsys):
    output_file = tmp_path / "bundle.json"
    rc = cmd_rdreview_prepare(
        "wi-review-1",
        "Test intent",
        str(output_file),
        output_format="bundle",
    )

    assert rc == 0
    assert output_file.exists()
    bundle = json.loads(output_file.read_text(encoding="utf-8"))
    assert bundle["kind"] == "rdreview_prepare_bundle"
    assert bundle["run_record"]["acceptance_state"] == "review_pending"
    captured = capsys.readouterr()
    assert "Review prepare bundle written to" in captured.out


def test_cmd_rdreview_with_routed_argv(tmp_path):
    """Regression: argv from app.py routing must not include 'rdreview'."""
    output_file = tmp_path / "packet.json"
    rc = cmd_rdreview(["wi-review-1", "test", "--output", str(output_file)])
    assert rc == 0
    assert output_file.exists()
    packet = json.loads(output_file.read_text(encoding="utf-8"))
    assert packet["work_item"]["id"] == "wi-review-1"
    assert packet["work_item"]["intent"] == "test"


def test_cmd_rdreview_with_bundle_format(tmp_path):
    output_file = tmp_path / "bundle.json"
    rc = cmd_rdreview([
        "wi-review-1",
        "test",
        "--format",
        "bundle",
        "--output",
        str(output_file),
    ])

    assert rc == 0
    bundle = json.loads(output_file.read_text(encoding="utf-8"))
    assert bundle["kind"] == "rdreview_prepare_bundle"
    assert bundle["work_item_id"] == "wi-review-1"


def test_devframe_rdreview_help_exposes_bundle_format(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "rdreview", "--help"])

    assert devframe_cli_main() == 0
    output = capsys.readouterr().out
    assert "--format packet|bundle" in output
    assert "prepare-only runtime-governance bundle" in output


def test_devframe_rdreview_bundle_through_top_level_router(tmp_path, monkeypatch):
    output_file = tmp_path / "bundle.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "rdreview",
            "wi-review-1",
            "test",
            "--format",
            "bundle",
            "--output",
            str(output_file),
        ],
    )

    assert devframe_cli_main() == 0
    bundle = json.loads(output_file.read_text(encoding="utf-8"))
    assert bundle["kind"] == "rdreview_prepare_bundle"
    _schema_validator("schemas/runtime-governance/context-packet.schema.json").validate(
        bundle["context_packet"]
    )
    _schema_validator("schemas/runtime-governance/context-ledger.schema.json").validate(
        bundle["context_ledger"]
    )
    _schema_validator("schemas/runtime-governance/run-record.schema.json").validate(
        bundle["run_record"]
    )
    _schema_validator("schemas/agent-runtime/task-spec.schema.json").validate(
        bundle["task_spec"]
    )
