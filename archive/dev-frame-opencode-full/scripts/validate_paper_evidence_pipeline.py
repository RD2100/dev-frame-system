"""validate_paper_evidence_pipeline.py — A9 Evidence Pipeline validation.

Runs 12 checks to verify the end-to-end evidence pipeline:
  1-3:  Module structure
  4-6:  Offline pipeline (handoff ZIP)
  7-9:  Live pipeline (call results)
  10-12: Integration (adapter→gate chain, schema validation)
"""

import sys
import json
import tempfile
import hashlib
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "ai-workflow-hub" / "src"))

from ai_workflow_hub.context_layer.adapters.paper_evidence_pipeline import (
    run_offline_pipeline,
    run_live_pipeline,
)
from ai_workflow_hub.context_layer.adapters.writelab_client import WriteLabCallResult
from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import (
    validate_acceptance_result,
)


def run_check(check_id: int, description: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] Check {check_id:02d}: {description}")
    if detail and not passed:
        print(f"         Detail: {detail}")
    return passed


def make_test_zip(tmp_dir: Path) -> Path:
    """Create a minimal handoff ZIP for validation."""
    expr = [{
        "detection_id": "val-0001", "rule_id": "W1", "risk_level": "high",
        "chapter": "引言", "section": "", "paragraph_index": 0,
        "rule_description": "test", "suggestion": "fix", "matched_text": "不是A而是B",
    }]
    expr_json = json.dumps(expr, ensure_ascii=False)
    para_json = json.dumps([], ensure_ascii=False)
    sha = hashlib.sha256(expr_json.encode("utf-8")).hexdigest()

    manifest = {
        "handoff_id": "val-001",
        "writelab_version": "0.1.0",
        "created_at": "2026-06-11T12:00:00Z",
        "task_id": "val-task",
        "privacy_attestation": {
            "no_full_text": True, "no_api_keys": True, "no_personal_identity": True,
        },
        "files": [
            {"path": "diagnosis/expression_results.json", "sha256": sha, "size_bytes": len(expr_json.encode())},
            {"path": "diagnosis/paragraph_results.json", "sha256": hashlib.sha256(para_json.encode()).hexdigest(), "size_bytes": len(para_json.encode())},
        ],
    }

    zip_path = tmp_dir / "val_handoff.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("diagnosis/expression_results.json", expr_json)
        zf.writestr("diagnosis/paragraph_results.json", para_json)
    return zip_path


def main():
    print("=" * 60)
    print("A9 Paper Evidence Pipeline Validation")
    print("=" * 60)

    results = []

    # --- Module structure (1-3) ---
    pipe_file = PROJECT_ROOT / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "context_layer" / "adapters" / "paper_evidence_pipeline.py"
    results.append(run_check(1, "paper_evidence_pipeline.py exists",
                             pipe_file.exists()))

    source = pipe_file.read_text(encoding="utf-8")
    results.append(run_check(2, "run_offline_pipeline defined",
                             "def run_offline_pipeline" in source))
    results.append(run_check(3, "run_live_pipeline defined",
                             "def run_live_pipeline" in source))

    # --- Offline pipeline (4-6) ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = make_test_zip(tmp_path)
        output = run_offline_pipeline(zip_path)

        results.append(run_check(4, "Offline pipeline returns acceptance_result + manifest",
                                 "acceptance_result" in output and "evidence_manifest" in output))

        ar = output["acceptance_result"]
        results.append(run_check(5, "Offline: blocking W1 → status=blocked",
                                 ar["status"] == "blocked" and len(ar["blocking_issues"]) >= 1))

        results.append(run_check(6, "Offline: evidence_pack_ref matches manifest_id",
                                 ar["evidence_pack_ref"] == output["evidence_manifest"]["manifest_id"]))

    # --- Live pipeline (7-9) ---
    live_output = run_live_pipeline(
        call_results=[WriteLabCallResult(success=True, issues=[], diagnosis_source="llm")],
        evidence_pack_ref="ep-val-live",
    )
    results.append(run_check(7, "Live pipeline: clean calls → accepted",
                             live_output["acceptance_result"]["status"] == "accepted"))

    degraded_result = run_live_pipeline(
        call_results=[WriteLabCallResult(success=False, issues=[], diagnosis_source="unavailable", error="test")],
        evidence_pack_ref="ep-val-deg",
    )
    results.append(run_check(8, "Live: unavailable adds +degraded to evidence_pack_ref",
                             "+degraded" in degraded_result["acceptance_result"]["evidence_pack_ref"]))

    results.append(run_check(9, "Live: call_summaries populated",
                             len(live_output["call_summaries"]) == 1))

    # --- Integration (10-12) ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = make_test_zip(tmp_path)
        output = run_offline_pipeline(zip_path)

        errors = validate_acceptance_result(output["acceptance_result"])
        results.append(run_check(10, "End-to-end result passes schema validation",
                                 errors == []))

        results.append(run_check(11, "No validation errors in pipeline output",
                                 output["validation_errors"] == []))

        # Check all issues have wl- prefix
        all_issues = output["acceptance_result"]["blocking_issues"] + output["acceptance_result"]["non_blocking_issues"]
        all_wl = all(i["issue_id"].startswith("wl-") for i in all_issues)
        results.append(run_check(12, "All issues have wl- prefix (adapter chain verified)",
                                 all_wl and len(all_issues) >= 1))

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
