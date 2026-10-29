"""test_writelab_adapter.py — A5 WriteLab Adapter integration tests.

Tests the full adapter pipeline using mock WriteLab fixtures:
  - Expression results conversion
  - Paragraph results conversion
  - Handoff ZIP import
  - Privacy attestation validation
  - Schema validation helpers
  - Full dry-run pipeline
  - Degraded/unavailable scenarios
"""

import json
import hashlib
import tempfile
import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths to fixtures
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / ".." / "src" / "ai_workflow_hub" / "context_layer" / "adapters" / "writelab_fixtures"
EXPR_FIXTURE = FIXTURES_DIR / "mock_expression_results.json"
PARA_FIXTURE = FIXTURES_DIR / "mock_paragraph_results.json"
ZIP_FIXTURE = FIXTURES_DIR / "mock_handoff.zip"

# Import adapter
from ai_workflow_hub.context_layer.adapters.writelab_adapter import (
    convert_expression_results,
    convert_paragraph_results,
    convert_handoff_zip,
    validate_privacy_attestation,
    validate_review_issue,
    validate_evidence_manifest,
    dry_run,
    PrivacyValidationResult,
    SEVERITY_MAP,
    BLOCKING_CORE_RULES,
)


# ===========================================================================
# TestPrivacyAttestation
# ===========================================================================
class TestPrivacyAttestation:

    def test_all_true_is_valid(self):
        att = {"no_full_text": True, "no_api_keys": True, "no_personal_identity": True}
        result = validate_privacy_attestation(att)
        assert result.valid is True
        assert result.errors == []

    def test_missing_key_rejected(self):
        att = {"no_full_text": True}  # missing two keys
        result = validate_privacy_attestation(att)
        assert result.valid is False
        assert len(result.errors) == 2

    def test_false_value_rejected(self):
        att = {"no_full_text": False, "no_api_keys": True, "no_personal_identity": True}
        result = validate_privacy_attestation(att)
        assert result.valid is False
        assert "privacy violation: full text detected" in result.errors

    def test_empty_dict_rejected(self):
        result = validate_privacy_attestation({})
        assert result.valid is False
        assert len(result.errors) == 3

    def test_all_false_rejected(self):
        att = {"no_full_text": False, "no_api_keys": False, "no_personal_identity": False}
        result = validate_privacy_attestation(att)
        assert result.valid is False
        assert len(result.errors) == 3


# ===========================================================================
# TestConvertExpressionResults
# ===========================================================================
class TestConvertExpressionResults:

    @pytest.fixture
    def expression_data(self):
        return json.loads(EXPR_FIXTURE.read_text(encoding="utf-8"))

    def test_count(self, expression_data):
        issues = convert_expression_results(expression_data)
        assert len(issues) == 8

    def test_issue_id_prefix(self, expression_data):
        issues = convert_expression_results(expression_data)
        for issue in issues:
            assert issue["issue_id"].startswith("wl-expr-")

    def test_issue_type_all_expression(self, expression_data):
        issues = convert_expression_results(expression_data)
        for issue in issues:
            assert issue["issue_type"] == "expression"

    def test_severity_mapping_high(self, expression_data):
        issues = convert_expression_results(expression_data)
        # detection_id 0001 has risk_level=high -> severity=major
        w1 = next(i for i in issues if "0001" in i["issue_id"])
        assert w1["severity"] == "major"

    def test_severity_mapping_medium(self, expression_data):
        issues = convert_expression_results(expression_data)
        # detection_id 0005 has risk_level=medium -> severity=minor
        dunhao = next(i for i in issues if "0005" in i["issue_id"])
        assert dunhao["severity"] == "minor"

    def test_severity_mapping_low(self, expression_data):
        issues = convert_expression_results(expression_data)
        # detection_id 0004 has risk_level=low -> severity=info
        w7 = next(i for i in issues if "0004" in i["issue_id"])
        assert w7["severity"] == "info"

    def test_blocking_core_rule_high_risk(self, expression_data):
        issues = convert_expression_results(expression_data)
        # W1 + high risk -> blocking
        w1 = next(i for i in issues if "0001" in i["issue_id"])
        assert w1["blocking"] is True

    def test_blocking_non_core_rule(self, expression_data):
        issues = convert_expression_results(expression_data)
        # W7 + low risk -> not blocking (even though W7 is core, risk is low)
        w7 = next(i for i in issues if "0004" in i["issue_id"])
        assert w7["blocking"] is False

    def test_evidence_with_matched_text(self, expression_data):
        issues = convert_expression_results(expression_data)
        w1 = next(i for i in issues if "0001" in i["issue_id"])
        assert "[W1]" in w1["evidence"]
        assert "不是" in w1["evidence"]

    def test_evidence_without_matched_text(self, expression_data):
        issues = convert_expression_results(expression_data)
        dunhao = next(i for i in issues if "0005" in i["issue_id"])
        assert "[DUNHAO]" in dunhao["evidence"]

    def test_human_required_false(self, expression_data):
        issues = convert_expression_results(expression_data)
        for issue in issues:
            assert issue["human_required"] is False

    def test_location_fields(self, expression_data):
        issues = convert_expression_results(expression_data)
        for issue in issues:
            assert "chapter" in issue["location"]
            assert "paragraph_index" in issue["location"]

    def test_schema_validation_passes(self, expression_data):
        issues = convert_expression_results(expression_data)
        for issue in issues:
            errors = validate_review_issue(issue)
            assert errors == [], f"Validation errors for {issue['issue_id']}: {errors}"

    def test_empty_input(self):
        issues = convert_expression_results([])
        assert issues == []


# ===========================================================================
# TestConvertParagraphResults
# ===========================================================================
class TestConvertParagraphResults:

    @pytest.fixture
    def paragraph_data(self):
        return json.loads(PARA_FIXTURE.read_text(encoding="utf-8"))

    def test_skips_well_matched(self, paragraph_data):
        """PD-003 has match_score=85 and no problems -> should be skipped."""
        issues = convert_paragraph_results(paragraph_data)
        ids = [i["issue_id"] for i in issues]
        assert "wl-para-PD-003" not in ids

    def test_count(self, paragraph_data):
        issues = convert_paragraph_results(paragraph_data)
        # PD-001, PD-002, PD-004, PD-005 have problems; PD-003 is skipped
        assert len(issues) == 4

    def test_issue_id_prefix(self, paragraph_data):
        issues = convert_paragraph_results(paragraph_data)
        for issue in issues:
            assert issue["issue_id"].startswith("wl-para-")

    def test_function_mismatch_is_structure(self, paragraph_data):
        issues = convert_paragraph_results(paragraph_data)
        pd001 = next(i for i in issues if "PD-001" in i["issue_id"])
        assert pd001["issue_type"] == "structure"

    def test_missing_evidence_is_argument(self, paragraph_data):
        issues = convert_paragraph_results(paragraph_data)
        pd002 = next(i for i in issues if "PD-002" in i["issue_id"])
        assert pd002["issue_type"] == "argument"

    def test_confidence_major(self, paragraph_data):
        """PD-004 confidence=0.35 -> severity=major."""
        issues = convert_paragraph_results(paragraph_data)
        pd004 = next(i for i in issues if "PD-004" in i["issue_id"])
        assert pd004["severity"] == "major"

    def test_confidence_minor(self, paragraph_data):
        """PD-002 confidence=0.55 -> severity=minor."""
        issues = convert_paragraph_results(paragraph_data)
        pd002 = next(i for i in issues if "PD-002" in i["issue_id"])
        assert pd002["severity"] == "minor"

    def test_confidence_info(self, paragraph_data):
        """PD-001 confidence=0.85 -> severity=info."""
        issues = convert_paragraph_results(paragraph_data)
        pd001 = next(i for i in issues if "PD-001" in i["issue_id"])
        assert pd001["severity"] == "info"

    def test_blocking_low_confidence(self, paragraph_data):
        """PD-004 confidence=0.35 < 0.4 -> blocking=true."""
        issues = convert_paragraph_results(paragraph_data)
        pd004 = next(i for i in issues if "PD-004" in i["issue_id"])
        assert pd004["blocking"] is True

    def test_no_blocking_high_confidence(self, paragraph_data):
        """PD-001 confidence=0.85 -> blocking=false."""
        issues = convert_paragraph_results(paragraph_data)
        pd001 = next(i for i in issues if "PD-001" in i["issue_id"])
        assert pd001["blocking"] is False

    def test_human_required_real_data(self, paragraph_data):
        """PD-004 involves_real_data=true -> human_required=true."""
        issues = convert_paragraph_results(paragraph_data)
        pd004 = next(i for i in issues if "PD-004" in i["issue_id"])
        assert pd004["human_required"] is True

    def test_human_required_no_real_data(self, paragraph_data):
        """PD-001 involves_real_data=false -> human_required=false."""
        issues = convert_paragraph_results(paragraph_data)
        pd001 = next(i for i in issues if "PD-001" in i["issue_id"])
        assert pd001["human_required"] is False

    def test_evidence_format(self, paragraph_data):
        issues = convert_paragraph_results(paragraph_data)
        for issue in issues:
            assert "期望=" in issue["evidence"]
            assert "实际=" in issue["evidence"]
            assert "置信度=" in issue["evidence"]

    def test_schema_validation_passes(self, paragraph_data):
        issues = convert_paragraph_results(paragraph_data)
        for issue in issues:
            errors = validate_review_issue(issue)
            assert errors == [], f"Validation errors for {issue['issue_id']}: {errors}"

    def test_empty_input(self):
        issues = convert_paragraph_results([])
        assert issues == []


# ===========================================================================
# TestConvertHandoffZip
# ===========================================================================
class TestConvertHandoffZip:

    def test_basic_conversion(self):
        manifest = convert_handoff_zip(ZIP_FIXTURE)
        assert manifest["manifest_id"] == "wl-wl-handoff-20260611-001"
        assert manifest["task_id"] == "paper-task-a5-dryrun"
        assert manifest["status"] == "complete"

    def test_file_count(self):
        manifest = convert_handoff_zip(ZIP_FIXTURE)
        assert len(manifest["files"]) == 5

    def test_file_integrity(self):
        manifest = convert_handoff_zip(ZIP_FIXTURE)
        for f in manifest["files"]:
            assert f.get("integrity") == "ok"

    def test_content_types(self):
        manifest = convert_handoff_zip(ZIP_FIXTURE)
        json_files = [f for f in manifest["files"] if f["filename"].endswith(".json")]
        yaml_files = [f for f in manifest["files"] if f["filename"].endswith(".yaml")]
        for f in json_files:
            assert f["content_type"] == "application/json"
        for f in yaml_files:
            assert f["content_type"] == "application/yaml"

    def test_privacy_attestation(self):
        manifest = convert_handoff_zip(ZIP_FIXTURE)
        pa = manifest["privacy_attestation"]
        assert pa["no_full_text"] is True
        assert pa["no_api_keys"] is True
        assert pa["no_personal_identity"] is True

    def test_schema_validation(self):
        manifest = convert_handoff_zip(ZIP_FIXTURE)
        errors = validate_evidence_manifest(manifest)
        assert errors == [], f"Validation errors: {errors}"

    def test_missing_zip_raises(self):
        with pytest.raises(FileNotFoundError):
            convert_handoff_zip("/nonexistent/path.zip")

    def test_privacy_violation_rejected(self, tmp_path):
        """Create a ZIP with privacy_attestation.no_full_text=false."""
        manifest_data = {
            "handoff_id": "bad-handoff",
            "task_id": "test",
            "created_at": "2026-01-01T00:00:00Z",
            "privacy_attestation": {
                "no_full_text": False,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
            "files": [],
        }
        zip_path = tmp_path / "bad_privacy.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))

        with pytest.raises(ValueError, match="privacy violation"):
            convert_handoff_zip(zip_path)

    def test_sha256_mismatch_partial(self, tmp_path):
        """Create a ZIP where one file's SHA doesn't match manifest."""
        file_data = b"original content"
        wrong_sha = "0" * 64

        manifest_data = {
            "handoff_id": "mismatch-handoff",
            "task_id": "test",
            "created_at": "2026-01-01T00:00:00Z",
            "privacy_attestation": {
                "no_full_text": True,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
            "files": [
                {"path": "data/test.json", "sha256": wrong_sha, "size_bytes": len(file_data)},
            ],
        }
        zip_path = tmp_path / "mismatch.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))
            zf.writestr("data/test.json", file_data)

        manifest = convert_handoff_zip(zip_path)
        assert manifest["status"] == "failed"  # no files match
        assert manifest["files"][0]["integrity"] == "mismatch"

    def test_missing_manifest_raises(self, tmp_path):
        zip_path = tmp_path / "no_manifest.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("data/test.json", "{}")

        with pytest.raises(ValueError, match="missing manifest"):
            convert_handoff_zip(zip_path)


# ===========================================================================
# TestValidateReviewIssue
# ===========================================================================
class TestValidateReviewIssue:

    def test_valid_expression_issue(self):
        issue = {
            "issue_id": "wl-expr-0001",
            "issue_type": "expression",
            "severity": "major",
            "evidence": "[W1] test",
            "blocking": True,
            "human_required": False,
        }
        assert validate_review_issue(issue) == []

    def test_missing_required_field(self):
        issue = {"issue_id": "wl-expr-0001", "issue_type": "expression"}
        errors = validate_review_issue(issue)
        assert len(errors) >= 2  # missing severity, evidence, blocking

    def test_invalid_issue_type(self):
        issue = {
            "issue_id": "wl-expr-0001",
            "issue_type": "invalid_type",
            "severity": "major",
            "evidence": "test",
            "blocking": True,
        }
        errors = validate_review_issue(issue)
        assert any("invalid issue_type" in e for e in errors)

    def test_invalid_severity(self):
        issue = {
            "issue_id": "wl-expr-0001",
            "issue_type": "expression",
            "severity": "extreme",
            "evidence": "test",
            "blocking": True,
        }
        errors = validate_review_issue(issue)
        assert any("invalid severity" in e for e in errors)

    def test_missing_wl_prefix(self):
        issue = {
            "issue_id": "expr-0001",
            "issue_type": "expression",
            "severity": "major",
            "evidence": "test",
            "blocking": True,
        }
        errors = validate_review_issue(issue)
        assert any("wl-" in e for e in errors)


# ===========================================================================
# TestValidateEvidenceManifest
# ===========================================================================
class TestValidateEvidenceManifest:

    def test_valid_manifest(self):
        manifest = {
            "manifest_id": "wl-test-001",
            "task_id": "test-task",
            "status": "complete",
            "files": [{"filename": "test.json", "sha256": "abc", "size_bytes": 100}],
            "privacy_attestation": {
                "no_full_text": True,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
        }
        assert validate_evidence_manifest(manifest) == []

    def test_missing_required(self):
        errors = validate_evidence_manifest({})
        assert len(errors) >= 4

    def test_invalid_status(self):
        manifest = {
            "manifest_id": "test",
            "task_id": "test",
            "status": "invalid",
            "files": [],
            "privacy_attestation": {
                "no_full_text": True,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
        }
        errors = validate_evidence_manifest(manifest)
        assert any("invalid status" in e for e in errors)


# ===========================================================================
# TestDryRun
# ===========================================================================
class TestDryRun:

    def test_full_dry_run(self):
        report = dry_run(
            expression_results_path=EXPR_FIXTURE,
            paragraph_results_path=PARA_FIXTURE,
            handoff_zip_path=ZIP_FIXTURE,
        )
        assert report["adapter_source"] == "writelab_adapter"
        assert len(report["expression_issues"]) == 8
        assert len(report["paragraph_issues"]) == 4
        assert report["evidence_manifest"] is not None
        assert report["evidence_manifest"]["status"] == "complete"

    def test_dry_run_no_validation_errors(self):
        report = dry_run(
            expression_results_path=EXPR_FIXTURE,
            paragraph_results_path=PARA_FIXTURE,
            handoff_zip_path=ZIP_FIXTURE,
        )
        assert report["validation_errors"] == {}

    def test_dry_run_expression_only(self):
        report = dry_run(expression_results_path=EXPR_FIXTURE)
        assert len(report["expression_issues"]) == 8
        assert report["paragraph_issues"] == []
        assert report["evidence_manifest"] is None

    def test_dry_run_paragraph_only(self):
        report = dry_run(paragraph_results_path=PARA_FIXTURE)
        assert len(report["paragraph_issues"]) == 4
        assert report["expression_issues"] == []

    def test_dry_run_no_inputs(self):
        report = dry_run()
        assert report["expression_issues"] == []
        assert report["paragraph_issues"] == []
        assert report["evidence_manifest"] is None
        assert report["validation_errors"] == {}

    def test_dry_run_nonexistent_files(self):
        report = dry_run(
            expression_results_path="/nonexistent/expr.json",
            paragraph_results_path="/nonexistent/para.json",
        )
        # Non-existent files are silently skipped
        assert report["expression_issues"] == []
        assert report["paragraph_issues"] == []

    def test_service_unavailable_semantics(self):
        """Simulate WriteLab unavailable: no fixtures provided."""
        report = dry_run()
        assert report["adapter_source"] == "writelab_adapter"
        assert report["expression_issues"] == []
        assert report["paragraph_issues"] == []
        # This is the degraded/unavailable case — no issues, no blocking


# ===========================================================================
# TestBlockingIssuesSummary
# ===========================================================================
class TestBlockingIssuesSummary:

    def test_blocking_count(self):
        """Count blocking issues across both expression and paragraph results."""
        expr = json.loads(EXPR_FIXTURE.read_text(encoding="utf-8"))
        para = json.loads(PARA_FIXTURE.read_text(encoding="utf-8"))

        expr_issues = convert_expression_results(expr)
        para_issues = convert_paragraph_results(para)

        all_issues = expr_issues + para_issues
        blocking = [i for i in all_issues if i["blocking"]]

        # W1 (high + core) = blocking, W3 (high + core) = blocking,
        # PD-004 (confidence 0.35 < 0.4) = blocking
        assert len(blocking) >= 3

    def test_all_issues_have_wl_prefix(self):
        expr = json.loads(EXPR_FIXTURE.read_text(encoding="utf-8"))
        para = json.loads(PARA_FIXTURE.read_text(encoding="utf-8"))

        all_issues = convert_expression_results(expr) + convert_paragraph_results(para)
        for issue in all_issues:
            assert issue["issue_id"].startswith("wl-"), f"Bad prefix: {issue['issue_id']}"

    def test_reviewer_tag(self):
        """Verify adapter_source can be used as reviewer='writelab_adapter'."""
        report = dry_run(
            expression_results_path=EXPR_FIXTURE,
            paragraph_results_path=PARA_FIXTURE,
        )
        assert report["adapter_source"] == "writelab_adapter"
