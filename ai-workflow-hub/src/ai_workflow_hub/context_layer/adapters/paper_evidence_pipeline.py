"""paper_evidence_pipeline.py — A9 End-to-End Evidence Pipeline.

Wires together:
  - A5 adapter (convert_handoff_zip, convert_expression_results, convert_paragraph_results)
  - A7 client (WriteLabLiteClient) — optional live mode
  - A8 gate (compute_acceptance, validate_acceptance_result)

Two modes:
  1. Offline (handoff ZIP): Load ZIP → extract issues → run gate
  2. Live (API): Call WriteLab Lite → collect issues → run gate

Both produce a validated PaperAcceptanceResult.

Design:
  - Pure pipeline, no hidden state
  - Privacy attestation flows from manifest → gate
  - manifest_id flows to evidence_pack_ref
  - Failed manifest → blocked status
  - Degraded/unavailable warnings preserved (never silently dropped)
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from ai_workflow_hub.context_layer.adapters.writelab_adapter import (
    convert_handoff_zip,
    convert_expression_results,
    convert_paragraph_results,
    validate_evidence_manifest,
)
from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import (
    compute_acceptance,
    validate_acceptance_result,
)


# ---------------------------------------------------------------------------
# Offline pipeline (handoff ZIP)
# ---------------------------------------------------------------------------

def run_offline_pipeline(
    zip_path: str | Path,
    reviewer: str = "writelab_adapter",
) -> dict[str, Any]:
    """Run the full offline review pipeline from a WriteLab handoff ZIP.

    Steps:
      1. Convert handoff ZIP → PaperEvidenceManifest
      2. Extract expression/paragraph results from ZIP
      3. Convert results → PaperReviewIssue[]
      4. Run acceptance gate with manifest privacy attestation
      5. Validate output

    Args:
        zip_path: Path to the WriteLab handoff ZIP file
        reviewer: Reviewer source tag (default: writelab_adapter)

    Returns:
        dict with keys:
          - acceptance_result: PaperAcceptanceResult dict
          - evidence_manifest: PaperEvidenceManifest dict
          - validation_errors: list[str] (empty if valid)
    """
    zip_path = Path(zip_path)

    # Step 1: Convert ZIP → manifest
    manifest = convert_handoff_zip(zip_path)
    manifest_errors = validate_evidence_manifest(manifest)

    # Step 2: Extract results from ZIP
    expr_issues: list[dict[str, Any]] = []
    para_issues: list[dict[str, Any]] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()

        # Expression results
        if "diagnosis/expression_results.json" in namelist:
            expr_data = json.loads(zf.read("diagnosis/expression_results.json"))
            if isinstance(expr_data, list):
                expr_issues = convert_expression_results(expr_data)

        # Paragraph results
        if "diagnosis/paragraph_results.json" in namelist:
            para_data = json.loads(zf.read("diagnosis/paragraph_results.json"))
            if isinstance(para_data, list):
                para_issues = convert_paragraph_results(para_data)

    all_issues = expr_issues + para_issues

    # Step 3: Determine manifest status impact
    manifest_status = manifest.get("status", "unknown")
    needs_evidence = manifest_status in ("failed", "unknown")

    # Step 4: Run acceptance gate
    privacy_attestation = manifest.get("privacy_attestation")
    result = compute_acceptance(
        issues=all_issues,
        reviewer=reviewer,
        evidence_pack_ref=manifest.get("manifest_id", ""),
        privacy_attestation=privacy_attestation,
        needs_more_evidence=needs_evidence,
    )

    # If manifest integrity failed, add a blocking issue
    if manifest_status == "failed":
        result["reasons"].insert(
            0,
            f"evidence manifest integrity check failed (status={manifest_status}); "
            f"some files may be corrupted or missing",
        )
        if result["status"] not in ("blocked",):
            result["status"] = "blocked"
            result["reasons"].insert(0, "evidence manifest integrity failure forces blocked status")

    # Step 5: Validate
    gate_errors = validate_acceptance_result(result)

    return {
        "acceptance_result": result,
        "evidence_manifest": manifest,
        "validation_errors": manifest_errors + gate_errors,
    }


# ---------------------------------------------------------------------------
# Live pipeline (HTTP API)
# ---------------------------------------------------------------------------

def run_live_pipeline(
    call_results: list[Any],
    reviewer: str = "writelab_adapter",
    evidence_pack_ref: str = "",
    privacy_attestation: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Run the live review pipeline from WriteLabLiteClient call results.

    Args:
        call_results: List of WriteLabCallResult objects from the client
        reviewer: Reviewer source tag
        evidence_pack_ref: Evidence pack reference (e.g., from version info)
        privacy_attestation: Optional privacy attestation dict

    Returns:
        dict with keys:
          - acceptance_result: PaperAcceptanceResult dict
          - validation_errors: list[str]
          - call_summaries: list of per-call summaries
    """
    all_issues: list[dict[str, Any]] = []
    call_summaries: list[dict[str, Any]] = []

    for cr in call_results:
        issues = getattr(cr, "issues", [])
        all_issues.extend(issues)
        call_summaries.append({
            "success": getattr(cr, "success", False),
            "diagnosis_source": getattr(cr, "diagnosis_source", "unknown"),
            "fallback_used": getattr(cr, "fallback_used", False),
            "issue_count": len(issues),
            "error": getattr(cr, "error", None),
        })

    # Determine if any call had availability issues
    any_unavailable = any(
        getattr(cr, "diagnosis_source", "") == "unavailable"
        for cr in call_results
    )
    if any_unavailable and evidence_pack_ref:
        evidence_pack_ref = f"{evidence_pack_ref}+degraded"

    result = compute_acceptance(
        issues=all_issues,
        reviewer=reviewer,
        evidence_pack_ref=evidence_pack_ref,
        privacy_attestation=privacy_attestation,
    )

    gate_errors = validate_acceptance_result(result)

    return {
        "acceptance_result": result,
        "validation_errors": gate_errors,
        "call_summaries": call_summaries,
    }
