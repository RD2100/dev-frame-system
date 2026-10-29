"""writelab_adapter.py — WriteLab Diagnosis -> Paper Domain Adapter (A5 dry-run).

Converts synthetic WriteLab diagnosis outputs into Paper Domain contracts:
  - ExpressionResults  -> PaperReviewIssue[]
  - ParagraphResults   -> PaperReviewIssue[]
  - Handoff ZIP        -> PaperEvidenceManifest

Design principles:
  - P-1: WriteLab code stays in its own repo; adapter lives in Paper Domain
  - P-3: Adapter does not read writelab.db, .env, or internal state
  - P-5: Degrade gracefully — WriteLab unavailable -> skip, don't block

Field mapping reference: docs/paper/WRITELAB_ADAPTER_PLAN.md sections 4.1-4.3, 5.1-5.4
"""

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_MAP = {
    "high": "major",
    "medium": "minor",
    "low": "info",
}

BLOCKING_CORE_RULES = {"W1", "W3", "W7"}

CONTENT_TYPE_MAP = {
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


# ---------------------------------------------------------------------------
# Privacy attestation validation
# ---------------------------------------------------------------------------

@dataclass
class PrivacyValidationResult:
    """Result of privacy attestation validation."""
    valid: bool
    no_full_text: bool = False
    no_api_keys: bool = False
    no_personal_identity: bool = False
    errors: list[str] = field(default_factory=list)


def validate_privacy_attestation(
    attestation: dict[str, Any],
) -> PrivacyValidationResult:
    """Validate the three required privacy attestation booleans.

    All three must be True. Any failure rejects the import.
    Fail-closed: missing keys default to False (rejected).
    """
    errors: list[str] = []
    checks = {
        "no_full_text": "privacy violation: full text detected",
        "no_api_keys": "privacy violation: API keys detected",
        "no_personal_identity": "privacy violation: personal identity detected",
    }
    results = {}
    for key, error_msg in checks.items():
        val = attestation.get(key, False)
        results[key] = bool(val)
        if not val:
            errors.append(error_msg)

    return PrivacyValidationResult(
        valid=len(errors) == 0,
        no_full_text=results["no_full_text"],
        no_api_keys=results["no_api_keys"],
        no_personal_identity=results["no_personal_identity"],
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Expression results -> PaperReviewIssue[]
# ---------------------------------------------------------------------------

def convert_expression_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert WriteLab expression_detector results to PaperReviewIssue[].

    Mapping (adapter plan section 4.1):
      - detection_id -> issue_id (prefixed wl-expr-)
      - fixed "expression" -> issue_type
      - risk_level -> severity (high->major, medium->minor, low->info)
      - chapter + paragraph_index -> location
      - matched_text + rule_description -> evidence
      - suggestion -> recommendation
      - high risk + core rules (W1, W3, W7) -> blocking=true
      - fixed false -> human_required
    """
    issues: list[dict[str, Any]] = []
    for r in results:
        detection_id = r.get("detection_id", "unknown")
        rule_id = r.get("rule_id", "")
        risk_level = r.get("risk_level", r.get("severity", "low"))

        severity = SEVERITY_MAP.get(risk_level, "info")
        blocking = (risk_level == "high" and rule_id in BLOCKING_CORE_RULES)

        # Build evidence string
        matched = r.get("matched_text") or ""
        desc = r.get("rule_description", "")
        if matched:
            evidence = f'[{rule_id}] {desc}: "{matched}"'
        else:
            evidence = f"[{rule_id}] {desc}"

        issue = {
            "issue_id": f"wl-expr-{detection_id}",
            "issue_type": "expression",
            "severity": severity,
            "location": {
                "chapter": r.get("chapter", ""),
                "section": r.get("section", ""),
                "paragraph_index": r.get("paragraph_index", 0),
            },
            "evidence": evidence,
            "recommendation": r.get("suggestion", ""),
            "blocking": blocking,
            "human_required": False,
        }
        issues.append(issue)
    return issues


# ---------------------------------------------------------------------------
# Paragraph results -> PaperReviewIssue[]
# ---------------------------------------------------------------------------

def _classify_paragraph_issue_type(problems: list[dict]) -> str:
    """Determine issue_type from paragraph diagnosis problems.

    - function_mismatch -> "structure"
    - missing_evidence  -> "argument"
    - default           -> "structure"
    """
    for p in problems:
        ptype = p.get("type", "")
        if ptype == "missing_evidence":
            return "argument"
    return "structure"


def _severity_from_confidence(confidence: float) -> str:
    """Map confidence to severity.

    < 0.4 -> major
    0.4-0.6 -> minor
    > 0.6 -> info
    """
    if confidence < 0.4:
        return "major"
    elif confidence <= 0.6:
        return "minor"
    return "info"


def convert_paragraph_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert WriteLab paragraph_diagnosis results to PaperReviewIssue[].

    Mapping (adapter plan section 4.2):
      - diagnosis_id -> issue_id (prefixed wl-para-)
      - condition -> issue_type (function_mismatch -> structure, missing_evidence -> argument)
      - confidence -> severity (<0.4 -> major, 0.4-0.6 -> minor, >0.6 -> info)
      - chapter + paragraph_index -> location
      - expected/actual function + confidence -> evidence
      - improvement_hint -> recommendation
      - confidence < 0.4 + thesis paragraph -> blocking
      - involves_real_data -> human_required

    Skips paragraphs with no problems (function_match_score > 70 and empty problems).
    """
    issues: list[dict[str, Any]] = []
    for r in results:
        problems = r.get("problems", [])
        match_score = r.get("function_match_score", 100)
        confidence = r.get("confidence", 1.0)

        # Skip well-matched paragraphs with no problems
        if not problems and match_score > 70:
            continue

        diagnosis_id = r.get("diagnosis_id", "unknown")
        expected = r.get("expected_function", "")
        actual = r.get("actual_function", "")
        involves_real_data = r.get("involves_real_data", False)

        issue_type = _classify_paragraph_issue_type(problems)
        severity = _severity_from_confidence(confidence)
        blocking = confidence < 0.4

        # Build evidence string
        evidence = (
            f"段落功能不匹配: 期望={expected}, 实际={actual}, "
            f"置信度={confidence:.2f}, 匹配分={match_score}"
        )

        # Get recommendation from first problem or overall_comment
        recommendation = ""
        if problems:
            recommendation = problems[0].get("revision_direction", "")
        if not recommendation:
            recommendation = r.get("overall_comment", "")

        issue = {
            "issue_id": f"wl-para-{diagnosis_id}",
            "issue_type": issue_type,
            "severity": severity,
            "location": {
                "chapter": r.get("chapter", ""),
                "section": r.get("section", ""),
                "paragraph_index": r.get("paragraph_index", 0),
            },
            "evidence": evidence,
            "recommendation": recommendation,
            "blocking": blocking,
            "human_required": involves_real_data,
        }
        issues.append(issue)
    return issues


# ---------------------------------------------------------------------------
# Handoff ZIP -> PaperEvidenceManifest
# ---------------------------------------------------------------------------

def _sha256_of_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _content_type_from_path(filepath: str) -> str:
    """Infer content type from file extension."""
    ext = Path(filepath).suffix.lower()
    return CONTENT_TYPE_MAP.get(ext, "application/octet-stream")


def convert_handoff_zip(
    zip_path: str | Path,
) -> dict[str, Any]:
    """Convert a WriteLab handoff ZIP into a PaperEvidenceManifest dict.

    Steps:
      1. Validate privacy attestation (section 5.4)
      2. Verify SHA-256 integrity of each file
      3. Map fields to PaperEvidenceManifest schema

    Raises:
      ValueError: If privacy attestation validation fails.
      FileNotFoundError: If zip_path doesn't exist.
      zipfile.BadZipFile: If the file is not a valid ZIP.
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"Handoff ZIP not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Read manifest.json
        if "manifest.json" not in zf.namelist():
            raise ValueError("Handoff ZIP missing manifest.json")

        manifest_data = json.loads(zf.read("manifest.json"))

        # Step 1: Privacy attestation validation
        attestation = manifest_data.get("privacy_attestation", {})
        privacy_result = validate_privacy_attestation(attestation)
        if not privacy_result.valid:
            raise ValueError(
                f"Handoff ZIP rejected: {'; '.join(privacy_result.errors)}"
            )

        # Step 2: SHA-256 integrity verification
        expected_files = manifest_data.get("files", [])
        files_info: list[dict[str, Any]] = []
        all_intact = True
        any_intact = False

        for file_entry in expected_files:
            fpath = file_entry.get("path", "")
            expected_sha = file_entry.get("sha256", "")
            expected_size = file_entry.get("size_bytes", 0)

            if fpath not in zf.namelist():
                all_intact = False
                files_info.append({
                    "filename": Path(fpath).name,
                    "sha256": expected_sha,
                    "size_bytes": expected_size,
                    "content_type": _content_type_from_path(fpath),
                    "integrity": "missing",
                })
                continue

            actual_data = zf.read(fpath)
            actual_sha = _sha256_of_bytes(actual_data)
            actual_size = len(actual_data)

            intact = (actual_sha == expected_sha and actual_size == expected_size)
            if intact:
                any_intact = True
            else:
                all_intact = False

            files_info.append({
                "filename": Path(fpath).name,
                "sha256": actual_sha,
                "size_bytes": actual_size,
                "content_type": _content_type_from_path(fpath),
                "integrity": "ok" if intact else "mismatch",
            })

        # Determine status
        if all_intact and expected_files:
            status = "complete"
        elif any_intact:
            status = "partial"
        else:
            status = "failed"

        # Build PaperEvidenceManifest
        handoff_id = manifest_data.get("handoff_id", "unknown")
        task_id = manifest_data.get("task_id", "unknown")

        manifest = {
            "manifest_id": f"wl-{handoff_id}",
            "task_id": task_id,
            "status": status,
            "files": files_info,
            "privacy_attestation": {
                "no_full_text": privacy_result.no_full_text,
                "no_api_keys": privacy_result.no_api_keys,
                "no_personal_identity": privacy_result.no_personal_identity,
            },
            "created_at": manifest_data.get(
                "created_at",
                datetime.now(timezone.utc).isoformat(),
            ),
        }

    return manifest


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

def validate_review_issue(issue: dict[str, Any]) -> list[str]:
    """Validate a PaperReviewIssue dict against required fields and enums.

    Returns list of validation errors (empty = valid).
    """
    errors: list[str] = []
    required = ["issue_id", "issue_type", "severity", "evidence", "blocking"]
    for r in required:
        if r not in issue:
            errors.append(f"missing required field: {r}")

    valid_types = {
        "structure", "argument", "citation", "expression",
        "format", "privacy", "methodology",
    }
    if "issue_type" in issue and issue["issue_type"] not in valid_types:
        errors.append(f"invalid issue_type: {issue['issue_type']}")

    valid_severities = {"critical", "major", "minor", "info"}
    if "severity" in issue and issue["severity"] not in valid_severities:
        errors.append(f"invalid severity: {issue['severity']}")

    if "blocking" in issue and not isinstance(issue["blocking"], bool):
        errors.append("blocking must be boolean")

    if "human_required" in issue and not isinstance(issue["human_required"], bool):
        errors.append("human_required must be boolean")

    # wl- prefix check
    if "issue_id" in issue and not issue["issue_id"].startswith("wl-"):
        errors.append(
            f"WriteLab issue_id must start with 'wl-': {issue['issue_id']}"
        )

    return errors


def validate_evidence_manifest(manifest: dict[str, Any]) -> list[str]:
    """Validate a PaperEvidenceManifest dict against required fields.

    Returns list of validation errors (empty = valid).
    """
    errors: list[str] = []
    required = ["manifest_id", "task_id", "status", "files", "privacy_attestation"]
    for r in required:
        if r not in manifest:
            errors.append(f"missing required field: {r}")

    valid_statuses = {"complete", "partial", "failed"}
    if "status" in manifest and manifest["status"] not in valid_statuses:
        errors.append(f"invalid status: {manifest['status']}")

    if "files" in manifest:
        if not isinstance(manifest["files"], list):
            errors.append("files must be an array")
        else:
            for i, f in enumerate(manifest["files"]):
                for fk in ["filename", "sha256", "size_bytes"]:
                    if fk not in f:
                        errors.append(f"files[{i}] missing: {fk}")

    if "privacy_attestation" in manifest:
        pa = manifest["privacy_attestation"]
        for pk in ["no_full_text", "no_api_keys", "no_personal_identity"]:
            if pk not in pa:
                errors.append(f"privacy_attestation missing: {pk}")
            elif pa[pk] is not True:
                errors.append(f"privacy_attestation.{pk} must be true")

    return errors


# ---------------------------------------------------------------------------
# Convenience: full dry-run pipeline
# ---------------------------------------------------------------------------

def dry_run(
    expression_results_path: str | Path | None = None,
    paragraph_results_path: str | Path | None = None,
    handoff_zip_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run a full adapter dry-run with optional fixture files.

    Returns a report dict with:
      - expression_issues: list of PaperReviewIssue (from expression results)
      - paragraph_issues: list of PaperReviewIssue (from paragraph results)
      - evidence_manifest: PaperEvidenceManifest dict (from handoff ZIP)
      - validation_errors: dict of validation errors per section
      - adapter_source: "writelab_adapter"
    """
    report: dict[str, Any] = {
        "adapter_source": "writelab_adapter",
        "expression_issues": [],
        "paragraph_issues": [],
        "evidence_manifest": None,
        "validation_errors": {},
    }

    # Expression results
    if expression_results_path:
        path = Path(expression_results_path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            issues = convert_expression_results(data)
            report["expression_issues"] = issues
            errs = []
            for issue in issues:
                errs.extend(validate_review_issue(issue))
            if errs:
                report["validation_errors"]["expression"] = errs

    # Paragraph results
    if paragraph_results_path:
        path = Path(paragraph_results_path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            issues = convert_paragraph_results(data)
            report["paragraph_issues"] = issues
            errs = []
            for issue in issues:
                errs.extend(validate_review_issue(issue))
            if errs:
                report["validation_errors"]["paragraph"] = errs

    # Handoff ZIP
    if handoff_zip_path:
        path = Path(handoff_zip_path)
        if path.exists():
            manifest = convert_handoff_zip(path)
            report["evidence_manifest"] = manifest
            errs = validate_evidence_manifest(manifest)
            if errs:
                report["validation_errors"]["manifest"] = errs

    return report
