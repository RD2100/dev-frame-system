"""validate_writelab_adapter.py — A5 adapter validation script.

Runs 14 checks to verify the WriteLab adapter dry-run pipeline:
  1-3:  Expression results conversion
  4-6:  Paragraph results conversion
  7-9:  Handoff ZIP import
  10-11: Privacy attestation
  12-13: Schema validation
  14:   Full dry-run pipeline
"""

import json
import sys
from pathlib import Path

# Add project to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "ai-workflow-hub" / "src"))

from ai_workflow_hub.context_layer.adapters.writelab_adapter import (
    convert_expression_results,
    convert_paragraph_results,
    convert_handoff_zip,
    validate_privacy_attestation,
    validate_review_issue,
    validate_evidence_manifest,
    dry_run,
)

FIXTURES_DIR = PROJECT_ROOT / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "context_layer" / "adapters" / "writelab_fixtures"
EXPR_FIXTURE = FIXTURES_DIR / "mock_expression_results.json"
PARA_FIXTURE = FIXTURES_DIR / "mock_paragraph_results.json"
ZIP_FIXTURE = FIXTURES_DIR / "mock_handoff.zip"


def run_check(check_id: int, description: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] Check {check_id:02d}: {description}")
    if detail and not passed:
        print(f"         Detail: {detail}")
    return passed


def main():
    print("=" * 60)
    print("A5 WriteLab Adapter Dry-Run Validation")
    print("=" * 60)

    results = []

    # --- Expression results (checks 1-3) ---
    expr_data = json.loads(EXPR_FIXTURE.read_text(encoding="utf-8"))
    expr_issues = convert_expression_results(expr_data)

    results.append(run_check(1, "Expression conversion produces issues",
                             len(expr_issues) > 0, f"Got {len(expr_issues)}"))

    results.append(run_check(2, "All expression issue_ids start with wl-expr-",
                             all(i["issue_id"].startswith("wl-expr-") for i in expr_issues)))

    results.append(run_check(3, "Expression issues have valid severities",
                             all(i["severity"] in {"critical", "major", "minor", "info"} for i in expr_issues)))

    # --- Paragraph results (checks 4-6) ---
    para_data = json.loads(PARA_FIXTURE.read_text(encoding="utf-8"))
    para_issues = convert_paragraph_results(para_data)

    results.append(run_check(4, "Paragraph conversion produces issues",
                             len(para_issues) > 0, f"Got {len(para_issues)}"))

    results.append(run_check(5, "All paragraph issue_ids start with wl-para-",
                             all(i["issue_id"].startswith("wl-para-") for i in para_issues)))

    results.append(run_check(6, "Paragraph issue_types are structure or argument",
                             all(i["issue_type"] in {"structure", "argument"} for i in para_issues)))

    # --- Handoff ZIP (checks 7-9) ---
    manifest = convert_handoff_zip(ZIP_FIXTURE)

    results.append(run_check(7, "Handoff ZIP converts to manifest",
                             manifest["manifest_id"].startswith("wl-")))

    results.append(run_check(8, "Manifest status is complete",
                             manifest["status"] == "complete", f"Got {manifest['status']}"))

    results.append(run_check(9, "Manifest has correct file count",
                             len(manifest["files"]) == 5, f"Got {len(manifest['files'])}"))

    # --- Privacy attestation (checks 10-11) ---
    valid_att = {"no_full_text": True, "no_api_keys": True, "no_personal_identity": True}
    priv_result = validate_privacy_attestation(valid_att)

    results.append(run_check(10, "Valid attestation passes",
                             priv_result.valid))

    invalid_att = {"no_full_text": False, "no_api_keys": True, "no_personal_identity": True}
    priv_result_bad = validate_privacy_attestation(invalid_att)

    results.append(run_check(11, "Invalid attestation rejected",
                             not priv_result_bad.valid and len(priv_result_bad.errors) == 1))

    # --- Schema validation (checks 12-13) ---
    all_issues = expr_issues + para_issues
    schema_errors = []
    for issue in all_issues:
        schema_errors.extend(validate_review_issue(issue))

    results.append(run_check(12, "All issues pass PaperReviewIssue schema",
                             len(schema_errors) == 0,
                             f"{len(schema_errors)} errors" if schema_errors else ""))

    manifest_errors = validate_evidence_manifest(manifest)
    results.append(run_check(13, "Manifest passes PaperEvidenceManifest schema",
                             len(manifest_errors) == 0,
                             f"{len(manifest_errors)} errors" if manifest_errors else ""))

    # --- Full dry-run (check 14) ---
    report = dry_run(
        expression_results_path=EXPR_FIXTURE,
        paragraph_results_path=PARA_FIXTURE,
        handoff_zip_path=ZIP_FIXTURE,
    )
    results.append(run_check(14, "Full dry-run completes with no validation errors",
                             report["validation_errors"] == {} and report["adapter_source"] == "writelab_adapter"))

    # Summary
    passed = sum(results)
    total = len(results)
    print("=" * 60)
    print(f"Result: {passed}/{total} checks passed")
    if passed == total:
        print("STATUS: ALL CHECKS PASSED")
    else:
        print(f"STATUS: {total - passed} CHECK(S) FAILED")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
