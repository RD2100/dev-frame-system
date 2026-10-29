"""test_paper_evidence_pipeline.py — A9 End-to-End Evidence Pipeline tests.

Tests the integration of A5 adapter + A8 gate:
  - Offline pipeline (handoff ZIP → manifest → issues → gate)
  - Live pipeline (call results → issues → gate)
  - Manifest integrity impact
  - Privacy attestation passthrough
  - Schema validation of pipeline output
"""

import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from ai_workflow_hub.context_layer.adapters.paper_evidence_pipeline import (
    run_offline_pipeline,
    run_live_pipeline,
)
from ai_workflow_hub.context_layer.adapters.writelab_client import WriteLabCallResult
from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import (
    validate_acceptance_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_handoff_zip(
    tmp_dir: Path,
    expression_results: list[dict] | None = None,
    paragraph_results: list[dict] | None = None,
    privacy_attestation: dict | None = None,
    corrupt_sha: bool = False,
) -> Path:
    """Create a mock WriteLab handoff ZIP for testing."""
    if privacy_attestation is None:
        privacy_attestation = {
            "no_full_text": True,
            "no_api_keys": True,
            "no_personal_identity": True,
        }

    expr_json = json.dumps(expression_results or [], ensure_ascii=False)
    para_json = json.dumps(paragraph_results or [], ensure_ascii=False)

    files_manifest = [
        {
            "path": "diagnosis/expression_results.json",
            "sha256": "wrong_hash" if corrupt_sha else _sha256(expr_json),
            "size_bytes": len(expr_json.encode("utf-8")),
        },
        {
            "path": "diagnosis/paragraph_results.json",
            "sha256": _sha256(para_json),
            "size_bytes": len(para_json.encode("utf-8")),
        },
    ]

    manifest = {
        "handoff_id": "test-handoff-001",
        "writelab_version": "0.1.0",
        "created_at": "2026-06-11T12:00:00Z",
        "task_id": "test-task-001",
        "privacy_attestation": privacy_attestation,
        "files": files_manifest,
    }

    zip_path = tmp_dir / "test_handoff.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("diagnosis/expression_results.json", expr_json)
        zf.writestr("diagnosis/paragraph_results.json", para_json)

    return zip_path


def _sha256(data: str) -> str:
    import hashlib
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


SAMPLE_EXPR_RESULTS = [
    {
        "detection_id": "pipe-0001",
        "rule_id": "W1",
        "risk_level": "high",
        "chapter": "引言",
        "section": "",
        "paragraph_index": 0,
        "rule_description": "双重模板结构",
        "suggestion": "拆分论点",
        "matched_text": "不是A而是B",
    }
]

SAMPLE_PARA_RESULTS = [
    {
        "diagnosis_id": "pipe-para-0001",
        "expected_function": "problem_statement",
        "detected_function": "抽象论述",
        "confidence": 0.35,
        "chapter": "方法论",
        "section": "",
        "paragraph_index": 1,
        "improvement_hint": "用具体问题替代",
        "involves_real_data": False,
    }
]


# ===========================================================================
# TestOfflinePipeline
# ===========================================================================
class TestOfflinePipeline:

    def test_basic_pipeline(self, tmp_path):
        zip_path = make_handoff_zip(
            tmp_path,
            expression_results=SAMPLE_EXPR_RESULTS,
            paragraph_results=SAMPLE_PARA_RESULTS,
        )
        output = run_offline_pipeline(zip_path)

        assert "acceptance_result" in output
        assert "evidence_manifest" in output
        assert output["validation_errors"] == []

        result = output["acceptance_result"]
        assert result["reviewer"] == "writelab_adapter"
        assert result["evidence_pack_ref"] == "wl-test-handoff-001"

    def test_issues_extracted_from_zip(self, tmp_path):
        zip_path = make_handoff_zip(
            tmp_path,
            expression_results=SAMPLE_EXPR_RESULTS,
        )
        output = run_offline_pipeline(zip_path)
        result = output["acceptance_result"]

        # Should have at least 1 issue from expression results
        all_issues = result["blocking_issues"] + result["non_blocking_issues"]
        assert len(all_issues) >= 1
        assert any(i["issue_id"].startswith("wl-expr-") for i in all_issues)

    def test_empty_zip_accepted(self, tmp_path):
        zip_path = make_handoff_zip(tmp_path, expression_results=[], paragraph_results=[])
        output = run_offline_pipeline(zip_path)
        result = output["acceptance_result"]
        assert result["status"] in ("accepted", "needs_more_evidence")

    def test_privacy_attestation_passthrough(self, tmp_path):
        """Privacy attestation from ZIP flows to gate."""
        bad_attestation = {
            "no_full_text": False,
            "no_api_keys": True,
            "no_personal_identity": True,
        }
        # This should raise from convert_handoff_zip's privacy check
        with pytest.raises(ValueError, match="privacy"):
            zip_path = make_handoff_zip(tmp_path, privacy_attestation=bad_attestation)
            run_offline_pipeline(zip_path)

    def test_corrupt_sha_blocks_or_degrades(self, tmp_path):
        """Corrupted SHA-256 should result in non-complete manifest."""
        zip_path = make_handoff_zip(
            tmp_path,
            expression_results=SAMPLE_EXPR_RESULTS,
            corrupt_sha=True,
        )
        output = run_offline_pipeline(zip_path)
        manifest = output["evidence_manifest"]
        # Manifest status should not be "complete"
        assert manifest["status"] != "complete"


# ===========================================================================
# TestOfflinePipelineSchema
# ===========================================================================
class TestOfflinePipelineSchema:

    def test_result_validates(self, tmp_path):
        zip_path = make_handoff_zip(
            tmp_path,
            expression_results=SAMPLE_EXPR_RESULTS,
            paragraph_results=SAMPLE_PARA_RESULTS,
        )
        output = run_offline_pipeline(zip_path)
        errors = validate_acceptance_result(output["acceptance_result"])
        assert errors == [], f"Schema errors: {errors}"

    def test_manifest_has_required_fields(self, tmp_path):
        zip_path = make_handoff_zip(tmp_path, expression_results=SAMPLE_EXPR_RESULTS)
        output = run_offline_pipeline(zip_path)
        manifest = output["evidence_manifest"]
        assert "manifest_id" in manifest
        assert "status" in manifest
        assert "files" in manifest
        assert "privacy_attestation" in manifest


# ===========================================================================
# TestLivePipeline
# ===========================================================================
class TestLivePipeline:

    def test_basic_live_pipeline(self):
        results = [
            WriteLabCallResult(
                success=True,
                issues=[],
                diagnosis_source="rules_fallback",
            ),
        ]
        output = run_live_pipeline(results, evidence_pack_ref="ep-live-001")

        assert output["acceptance_result"]["status"] == "accepted"
        assert output["validation_errors"] == []
        assert len(output["call_summaries"]) == 1

    def test_live_with_issues(self):
        from ai_workflow_hub.context_layer.adapters.writelab_adapter import convert_expression_results

        issues = convert_expression_results(SAMPLE_EXPR_RESULTS)
        results = [
            WriteLabCallResult(
                success=True,
                issues=issues,
                diagnosis_source="rules_fallback",
            ),
        ]
        output = run_live_pipeline(results, evidence_pack_ref="ep-live-002")
        ar = output["acceptance_result"]

        assert ar["status"] == "blocked"  # W1 high → blocking
        assert len(ar["blocking_issues"]) >= 1

    def test_live_degraded_marks_evidence_ref(self):
        """Unavailable calls add '+degraded' suffix to evidence_pack_ref."""
        results = [
            WriteLabCallResult(
                success=False,
                issues=[],
                diagnosis_source="unavailable",
                error="connection refused",
            ),
        ]
        output = run_live_pipeline(results, evidence_pack_ref="ep-live-003")
        assert "+degraded" in output["acceptance_result"]["evidence_pack_ref"]

    def test_live_multiple_calls(self):
        results = [
            WriteLabCallResult(success=True, issues=[], diagnosis_source="llm"),
            WriteLabCallResult(success=True, issues=[], diagnosis_source="rules_fallback"),
            WriteLabCallResult(
                success=False, issues=[], diagnosis_source="unavailable",
                error="timeout",
            ),
        ]
        output = run_live_pipeline(results)
        assert len(output["call_summaries"]) == 3
        assert output["call_summaries"][2]["success"] is False

    def test_live_result_validates(self):
        results = [
            WriteLabCallResult(success=True, issues=[], diagnosis_source="llm"),
        ]
        output = run_live_pipeline(results, evidence_pack_ref="ep-validate")
        errors = validate_acceptance_result(output["acceptance_result"])
        assert errors == []

    def test_live_empty_results(self):
        output = run_live_pipeline([])
        assert output["acceptance_result"]["status"] == "accepted"
        assert output["call_summaries"] == []


# ===========================================================================
# TestEndToEndIntegration
# ===========================================================================
class TestEndToEndIntegration:

    def test_full_chain_adapter_gate(self, tmp_path):
        """A5 adapter → A8 gate: handoff ZIP to acceptance result."""
        zip_path = make_handoff_zip(
            tmp_path,
            expression_results=SAMPLE_EXPR_RESULTS,
            paragraph_results=SAMPLE_PARA_RESULTS,
        )
        output = run_offline_pipeline(zip_path)

        # Check chain integrity
        ar = output["acceptance_result"]
        manifest = output["evidence_manifest"]

        # evidence_pack_ref should match manifest_id
        assert ar["evidence_pack_ref"] == manifest["manifest_id"]

        # Privacy attestation should flow through
        assert manifest["privacy_attestation"]["no_full_text"] is True

        # All issues should have wl- prefix
        for issue in ar["blocking_issues"] + ar["non_blocking_issues"]:
            assert issue["issue_id"].startswith("wl-")

    def test_blocking_issue_blocks_pipeline(self, tmp_path):
        """High-risk W1 issue should result in blocked pipeline."""
        zip_path = make_handoff_zip(
            tmp_path,
            expression_results=SAMPLE_EXPR_RESULTS,  # W1 high → blocking
        )
        output = run_offline_pipeline(zip_path)
        assert output["acceptance_result"]["status"] == "blocked"
