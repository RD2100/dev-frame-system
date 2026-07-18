"""In-package validation gates for the synthetic paper pipeline."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
import zipfile

from jsonschema import Draft202012Validator, FormatChecker
import yaml


PAPER_TASK_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "task_id",
        "task_type",
        "paper_data_classification",
        "user_authorization",
        "input_materials",
        "privacy_constraints",
        "memory_policy",
        "expected_outputs",
    ],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "task_type": {
            "type": "string",
            "enum": [
                "cssci_review",
                "thesis_midterm_review",
                "academic_revision",
                "citation_verification",
                "paper_structure_diagnosis",
            ],
        },
        "paper_data_classification": {
            "type": "string",
            "enum": [
                "synthetic",
                "redacted",
                "user_authorized_excerpt",
                "real_paper_full_text",
            ],
        },
        "user_authorization": {
            "type": "string",
            "enum": ["explicit", "none", "synthetic"],
        },
        "input_materials": {"type": "array", "items": {"type": "string"}},
        "privacy_constraints": {"type": "array", "items": {"type": "string"}},
        "memory_policy": {
            "type": "string",
            "enum": ["none", "redacted_workflow_lesson_only"],
        },
        "expected_outputs": {"type": "array", "items": {"type": "string"}},
    },
}

PAPER_TASK_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "task_id",
        "task_type",
        "output_summary",
        "findings",
        "evidence_basis",
        "privacy_redaction_status",
        "manual_review_required",
        "limitations",
    ],
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "task_type": {"type": "string", "minLength": 1},
        "output_summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "object"}},
        "evidence_basis": {"type": "string"},
        "privacy_redaction_status": {
            "type": "string",
            "enum": ["full", "partial", "none"],
        },
        "manual_review_required": {"type": "boolean"},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "contains_real_paper_full_text": {"type": "boolean"},
        "contains_unredacted_excerpt": {"type": "boolean"},
        "contains_user_identity": {"type": "boolean"},
    },
}

_PAPER_FILES = (
    "PAPER_TASK_INPUT.yaml",
    "PAPER_TASK_OUTPUT.yaml",
    "PRIVACY_ATTESTATION.yaml",
)
_FORBIDDEN_SOURCE_NAMES = {"live_handoff_transfer.py", "submit_to_gpt.py"}
_LIVE_BROWSER_SOURCE = "playwright_bridge.py"
_PAPER_ENTRY_SOURCE = "stage_executor.py"
_FORBIDDEN_BROWSER_MODULES = {"playwright.sync_api", "playwright.async_api"}
_FORBIDDEN_BROWSER_CALLS = {
    "sync_playwright",
    "async_playwright",
    "connect_over_cdp",
    "goto",
}
_PAPER_REVIEW_EVIDENCE = (
    "TASKSPEC.json",
    "execution-report.json",
    "closure/FLOW_OUTCOME.json",
    "evidence/PAPER_PIPELINE_GATE.json",
    "evidence/ref-paper-review-pack.zip",
)


@dataclass(frozen=True)
class PaperPipelineGateResult:
    status: str
    errors: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        return payload


def _load_yaml(text: str, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        errors.append(f"{label}: invalid YAML: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label}: expected a YAML mapping")
        return {}
    return payload


def _read_paper_files(source: Path) -> tuple[dict[str, str], list[str]]:
    contents: dict[str, str] = {}
    errors: list[str] = []
    if source.is_dir():
        for name in _PAPER_FILES:
            candidates = (source / name, source / "paper_task" / name)
            path = next((item for item in candidates if item.is_file()), None)
            if path is None:
                errors.append(f"missing paper task artifact: {name}")
                continue
            contents[name] = path.read_text(encoding="utf-8")
        return contents, errors

    if not source.is_file() or not zipfile.is_zipfile(source):
        return contents, [f"paper task source is not a directory or ZIP: {source}"]

    with zipfile.ZipFile(source, "r") as archive:
        names = set(archive.namelist())
        for name in _PAPER_FILES:
            member = f"paper_task/{name}"
            if member not in names:
                errors.append(f"missing paper task artifact: {member}")
                continue
            try:
                contents[name] = archive.read(member).decode("utf-8")
            except UnicodeDecodeError as exc:
                errors.append(f"{member}: invalid UTF-8: {exc}")
    return contents, errors


def _schema_errors(schema: dict[str, Any], payload: dict[str, Any], label: str) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        f"{label}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    ]


def validate_paper_task_source(source: str | Path) -> PaperPipelineGateResult:
    source_path = Path(source).resolve()
    contents, errors = _read_paper_files(source_path)
    payloads = {
        name: _load_yaml(text, name, errors)
        for name, text in contents.items()
    }
    paper_input = payloads.get("PAPER_TASK_INPUT.yaml", {})
    paper_output = payloads.get("PAPER_TASK_OUTPUT.yaml", {})
    privacy = payloads.get("PRIVACY_ATTESTATION.yaml", {})

    if paper_input:
        errors.extend(_schema_errors(PAPER_TASK_INPUT_SCHEMA, paper_input, "PAPER_TASK_INPUT.yaml"))
    if paper_output:
        errors.extend(_schema_errors(PAPER_TASK_OUTPUT_SCHEMA, paper_output, "PAPER_TASK_OUTPUT.yaml"))

    task_ids = (
        paper_input.get("task_id"),
        paper_output.get("task_id"),
        privacy.get("task_id"),
    )
    if any(not isinstance(value, str) or not value.strip() for value in task_ids):
        errors.append("paper task artifacts require three non-empty task_id values")
    elif len(set(task_ids)) != 1:
        errors.append("paper task artifacts use different task_id values")
    input_task_type = paper_input.get("task_type")
    output_task_type = paper_output.get("task_type")
    if input_task_type and output_task_type and input_task_type != output_task_type:
        errors.append("paper task input and output use different task_type values")
    if paper_input.get("paper_data_classification") != "synthetic":
        errors.append("synthetic pipeline requires synthetic paper_data_classification")
        if paper_input.get("paper_data_classification") == "real_paper_full_text":
            errors.append("real paper full text is forbidden in the synthetic pipeline")
    if paper_input.get("user_authorization") != "synthetic":
        errors.append("synthetic pipeline requires synthetic user_authorization")

    for field_name in (
        "contains_real_paper_full_text",
        "contains_user_private_text",
        "contains_raw_transcript",
        "contains_external_upload",
    ):
        if privacy.get(field_name) is not False:
            errors.append(f"PRIVACY_ATTESTATION.yaml: {field_name} must be false")
    if privacy.get("redaction_applied") is not True:
        errors.append("PRIVACY_ATTESTATION.yaml: redaction_applied must be true")
    for field_name in (
        "contains_real_paper_full_text",
        "contains_unredacted_excerpt",
        "contains_user_identity",
    ):
        if paper_output.get(field_name) is not False:
            errors.append(f"PAPER_TASK_OUTPUT.yaml: {field_name} must be false")

    return PaperPipelineGateResult(
        status="pass" if not errors else "fail",
        errors=tuple(errors),
        details={"source": str(source_path), "validated_files": sorted(contents)},
    )


def _browser_operations(path: Path) -> tuple[ast.AST | None, list[str], str | None]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return None, [], str(exc)

    operations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_BROWSER_MODULES:
                    operations.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module in _FORBIDDEN_BROWSER_MODULES:
                operations.add(str(node.module))
                operations.update(
                    alias.name
                    for alias in node.names
                    if alias.name in _FORBIDDEN_BROWSER_CALLS
                )
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in _FORBIDDEN_BROWSER_CALLS:
                operations.add(name)
    return tree, sorted(operations), None


def _local_imports(tree: ast.AST, root: Path) -> set[Path]:
    targets: set[Path] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom):
            if node.level:
                if node.module:
                    modules.append(node.module)
                else:
                    modules.extend(alias.name for alias in node.names)
            elif node.module and node.module.startswith("control_plane."):
                modules.append(node.module.removeprefix("control_plane."))
        elif isinstance(node, ast.Import):
            modules.extend(
                alias.name.removeprefix("control_plane.")
                for alias in node.names
                if alias.name.startswith("control_plane.")
            )
        for module in modules:
            candidate = root.joinpath(*module.split("."))
            module_path = candidate.with_suffix(".py")
            package_path = candidate / "__init__.py"
            if module_path.is_file():
                targets.add(module_path.resolve())
            elif package_path.is_file():
                targets.add(package_path.resolve())
    return targets


def _paper_reachable_sources(root: Path, parsed: dict[Path, ast.AST]) -> set[Path]:
    entry = (root / _PAPER_ENTRY_SOURCE).resolve()
    if entry not in parsed:
        return set()
    pending = [entry]
    reachable: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in reachable:
            continue
        reachable.add(path)
        pending.extend(
            candidate
            for candidate in _local_imports(parsed[path], root) - reachable
            if candidate in parsed
        )
    return reachable


def scan_submission_bypass(source_root: str | Path | None = None) -> PaperPipelineGateResult:
    root = Path(source_root).resolve() if source_root else Path(__file__).resolve().parent
    errors: list[str] = []
    if not root.is_dir():
        return PaperPipelineGateResult(
            status="fail",
            errors=(f"submission source root is not a directory: {root}",),
            details={"source_root": str(root), "python_files_scanned": 0},
        )
    scanned = 0
    parsed: dict[Path, ast.AST] = {}
    browser_operations: dict[Path, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        relative = path.relative_to(root).as_posix()
        if path.name in _FORBIDDEN_SOURCE_NAMES:
            errors.append(f"forbidden submission source: {relative}")
            continue
        tree, operations, parse_error = _browser_operations(path)
        if parse_error:
            errors.append(f"cannot inspect submission source {relative}: {parse_error}")
            continue
        resolved = path.resolve()
        parsed[resolved] = tree
        if operations:
            browser_operations[resolved] = operations

    reachable = _paper_reachable_sources(root, parsed)
    shipped_root = Path(__file__).resolve().parent
    shipped_bridge = (shipped_root / _LIVE_BROWSER_SOURCE).resolve()
    for path, operations in browser_operations.items():
        relative = path.relative_to(root).as_posix()
        if path == shipped_bridge and root == shipped_root and path not in reachable:
            continue
        errors.append(
            f"unapproved browser submission operations {operations!r}: {relative}"
        )
    if shipped_bridge in reachable:
        errors.append("live browser bridge is reachable from the synthetic paper pipeline")

    return PaperPipelineGateResult(
        status="pass" if not errors else "fail",
        errors=tuple(errors),
        details={
            "source_root": str(root),
            "python_files_scanned": scanned,
            "paper_reachable_sources": sorted(
                path.relative_to(root).as_posix() for path in reachable
            ),
        },
    )


def _safe_zip_member(name: str) -> bool:
    if not name or "\\" in name or re.match(r"^[A-Za-z]:", name):
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def validate_evidence_pack(
    source: str | Path,
    *,
    content_root: str | Path | None = None,
) -> PaperPipelineGateResult:
    path = Path(source).resolve()
    errors: list[str] = []
    entries: dict[str, str] = {}
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                errors.append("evidence pack contains duplicate ZIP entries")
            for name in names:
                if not _safe_zip_member(name):
                    errors.append(f"evidence pack contains unsafe path: {name}")
            if names.count("PACK_MANIFEST.md") != 1:
                errors.append("evidence pack requires exactly one PACK_MANIFEST.md")
                manifest_text = ""
            else:
                try:
                    manifest_text = archive.read("PACK_MANIFEST.md").decode("utf-8")
                except UnicodeDecodeError as exc:
                    errors.append(f"PACK_MANIFEST.md is not UTF-8: {exc}")
                    manifest_text = ""

            for line in manifest_text.splitlines():
                if not line.startswith("|"):
                    continue
                parts = [part.strip() for part in line.split("|")[1:-1]]
                if len(parts) < 3 or parts[0] in {"path", "------"}:
                    continue
                member, digest = parts[0], parts[2]
                if member in entries:
                    errors.append(f"manifest contains duplicate path: {member}")
                entries[member] = digest

            zip_names = set(names)
            manifest_names = set(entries)
            if zip_names != manifest_names:
                missing = sorted(zip_names - manifest_names)
                extra = sorted(manifest_names - zip_names)
                if missing:
                    errors.append(f"files in ZIP but not manifest: {missing}")
                if extra:
                    errors.append(f"files in manifest but not ZIP: {extra}")
            for member, expected in entries.items():
                if member == "PACK_MANIFEST.md" and expected == "self_excluded":
                    continue
                if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
                    errors.append(f"manifest has invalid sha256 for {member}")
                    continue
                if member not in zip_names:
                    continue
                actual = hashlib.sha256(archive.read(member)).hexdigest()
                if actual.lower() != expected.lower():
                    errors.append(f"sha256 mismatch for {member}")

            count_match = re.search(r"(?m)^files_count:\s*(\d+)\s*$", manifest_text)
            if not count_match:
                errors.append("manifest requires files_count")
            elif int(count_match.group(1)) != len(names):
                errors.append("manifest files_count does not match ZIP entry count")
            valid_match = re.search(
                r"(?mi)^manifest_valid:\s*(true|false)\s*$",
                manifest_text,
            )
            if not valid_match or valid_match.group(1).lower() != "true":
                errors.append("manifest_valid must be true")

            if content_root is not None:
                root = Path(content_root).resolve()
                for member, expected in entries.items():
                    if member == "PACK_MANIFEST.md" or not _safe_zip_member(member):
                        continue
                    member_path = root.joinpath(*PurePosixPath(member).parts).resolve()
                    try:
                        member_path.relative_to(root)
                    except ValueError:
                        errors.append(f"manifest path is outside current project: {member}")
                        continue
                    if not member_path.is_file():
                        errors.append(f"current project file is missing: {member}")
                        continue
                    actual = hashlib.sha256(member_path.read_bytes()).hexdigest()
                    if actual.lower() != expected.lower():
                        errors.append(f"current project sha256 mismatch: {member}")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"invalid evidence pack: {exc}")

    return PaperPipelineGateResult(
        status="pass" if not errors else "fail",
        errors=tuple(errors),
        details={
            "source": str(path),
            "zip_entries": len(entries),
        },
    )


def _read_json_object(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: invalid JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label}: expected a JSON object")
        return {}
    return payload


def _project_relative_path(root: Path, value: Any) -> tuple[str, Path] | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return None
    return relative, resolved


def validate_paper_independent_review(
    project_root: str | Path,
    review_source: str | Path,
    expected_review_sha256: str,
    expected_reviewer_id: str,
) -> PaperPipelineGateResult:
    root = Path(project_root).resolve()
    source = Path(review_source).resolve()
    errors: list[str] = []
    if not root.is_dir():
        errors.append(f"paper project is not a directory: {root}")
    try:
        source.relative_to(root)
    except ValueError:
        pass
    else:
        errors.append("independent review source must be outside the paper project")

    expected_hash = str(expected_review_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        errors.append("independent review requires an explicit sha256 attestation")
    elif source.is_file():
        actual_review_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual_review_hash != expected_hash:
            errors.append("independent review sha256 attestation mismatch")
    review = _read_json_object(source, "independent review", errors)
    execution_report = _read_json_object(
        root / "execution-report.json",
        "execution-report.json",
        errors,
    )
    if review:
        review_schema_path = Path(__file__).resolve().parent / "gpt-review-result.schema.json"
        review_schema = json.loads(review_schema_path.read_text(encoding="utf-8"))
        review_errors = sorted(
            Draft202012Validator(
                review_schema,
                format_checker=FormatChecker(),
            ).iter_errors(review),
            key=lambda error: list(error.path),
        )
        errors.extend(
            f"independent review schema invalid: {error.message}"
            for error in review_errors
        )

    if execution_report.get("status") != "escalate":
        errors.append("execution report must be an escalation awaiting review")
    if execution_report.get("review_status") != "submitted":
        errors.append("execution report review_status must be submitted")
    if execution_report.get("blocking_issues") != ["independent_review_required"]:
        errors.append("execution report must be blocked only on independent review")

    flow = _read_json_object(
        root / "closure" / "FLOW_OUTCOME.json",
        "closure/FLOW_OUTCOME.json",
        errors,
    )
    expected_flow = {
        "synthetic_only": True,
        "submission_mode": "dry_run",
        "live_cdp_used": False,
        "bypass_detected": False,
        "final_status": "review_pending",
        "final_verdict_state": "deferred",
    }
    for field_name, expected in expected_flow.items():
        if flow.get(field_name) != expected:
            errors.append(
                f"FLOW_OUTCOME.json: {field_name} must be {expected!r}"
            )

    pipeline_gate = _read_json_object(
        root / "evidence" / "PAPER_PIPELINE_GATE.json",
        "evidence/PAPER_PIPELINE_GATE.json",
        errors,
    )
    if pipeline_gate.get("status") != "pass":
        errors.append("paper pipeline gate must pass before finalization")
    gate_details = pipeline_gate.get("details")
    if not isinstance(gate_details, dict) or gate_details.get("synthetic_only") is not True:
        errors.append("paper pipeline gate must attest synthetic_only")

    review_id = str(review.get("REVIEW_RUN_ID") or "").strip()
    executor_id = str(execution_report.get("executor_id") or "").strip()
    attested_reviewer_id = str(expected_reviewer_id or "").strip()
    if not review_id:
        errors.append("independent review requires REVIEW_RUN_ID")
    if not attested_reviewer_id:
        errors.append("independent review requires an explicit reviewer identity attestation")
    elif review_id != attested_reviewer_id:
        errors.append("independent review identity attestation mismatch")
    if not executor_id:
        errors.append("execution report requires executor_id")
    if review_id and executor_id and review_id == executor_id:
        errors.append("reviewer identity matches executor identity")
    if review.get("template_version") != "gpt-review-template-v1":
        errors.append("independent review requires gpt-review-template-v1")
    if review.get("task_type") != "paper_revision_review":
        errors.append("independent review task_type must be paper_revision_review")
    if review.get("review_stage") != "closure":
        errors.append("independent review stage must be closure")
    if review.get("reviewer_type") not in {"gpt", "human", "agent"}:
        errors.append("independent review requires a recognized reviewer_type")
    if review.get("overall_judgment") != "accepted" or review.get("allow_proceed") is not True:
        errors.append("independent review must explicitly accept and allow proceed")
    if review.get("blocking_reasons") != [] or review.get("missing_evidence") != []:
        errors.append("independent review contains blocking or missing evidence")
    for field_name in ("scope_violation", "fake_green_risk"):
        if review.get(field_name) is not False:
            errors.append(f"independent review {field_name} must be false")
    if review.get("safety_boundaries_respected") is not True:
        errors.append("independent review must confirm safety boundaries")
    if not str(review.get("rationale") or "").strip():
        errors.append("independent review requires rationale")
    if not str(review.get("created_at") or "").strip():
        errors.append("independent review requires created_at")
    if set((review.get("task_type_specific") or {}).keys()) != {"paper_revision_review"}:
        errors.append("task_type_specific must contain only paper_revision_review")
    authorization = review.get("next_task_authorization")
    if not isinstance(authorization, dict) or not str(authorization.get("task_id") or "").strip():
        errors.append("accepted review requires next_task_authorization")

    pack_path = root / "evidence" / "ref-paper-review-pack.zip"
    pack_result = validate_evidence_pack(pack_path)
    errors.extend(pack_result.errors)
    pack_meta = review.get("evidence_pack")
    if not isinstance(pack_meta, dict):
        errors.append("independent review requires evidence_pack metadata")
    else:
        resolved_pack = _project_relative_path(root, pack_meta.get("path"))
        if not resolved_pack or resolved_pack[1] != pack_path.resolve():
            errors.append("independent review evidence_pack path does not match the paper pack")
        if pack_meta.get("manifest_valid") is not True:
            errors.append("independent review must confirm a valid pack manifest")
        expected_pack_hash = hashlib.sha256(pack_path.read_bytes()).hexdigest() if pack_path.is_file() else ""
        if str(pack_meta.get("sha256") or "").lower() != expected_pack_hash:
            errors.append("independent review evidence_pack sha256 mismatch")

    inspected: dict[str, dict[str, Any]] = {}
    raw_evidence = review.get("evidence_inspected")
    if not isinstance(raw_evidence, list):
        errors.append("independent review evidence_inspected must be a list")
        raw_evidence = []
    for item in raw_evidence:
        if not isinstance(item, dict):
            errors.append("independent review evidence entry must be an object")
            continue
        resolved = _project_relative_path(root, item.get("path"))
        if not resolved:
            errors.append(f"independent review evidence path is outside the project: {item.get('path')}")
            continue
        relative, evidence_path = resolved
        if relative in inspected:
            errors.append(f"independent review repeats evidence path: {relative}")
            continue
        inspected[relative] = item
        if item.get("inspected") is not True:
            errors.append(f"independent review did not inspect: {relative}")
        if not evidence_path.is_file():
            errors.append(f"independent review evidence is missing: {relative}")
            continue
        actual_hash = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        if str(item.get("sha256") or "").lower() != actual_hash:
            errors.append(f"independent review evidence sha256 mismatch: {relative}")
    for relative in _PAPER_REVIEW_EVIDENCE:
        if relative not in inspected:
            errors.append(f"independent review did not cover required evidence: {relative}")

    return PaperPipelineGateResult(
        status="pass" if not errors else "fail",
        errors=tuple(errors),
        details={
            "project_root": str(root),
            "review_source": str(source),
            "review_sha256": expected_hash,
            "review_id": review_id,
            "executor_id": executor_id,
            "reviewed_evidence": sorted(inspected),
        },
    )


def finalize_paper_project(
    project_root: str | Path,
    review_source: str | Path,
    expected_review_sha256: str,
    expected_reviewer_id: str,
) -> PaperPipelineGateResult:
    root = Path(project_root).resolve()
    final_path = root / "closure" / "FINAL_VERDICT.json"
    alternate_final_path = root / "closure" / "final-verdict.json"
    if final_path.exists() or alternate_final_path.exists():
        return PaperPipelineGateResult(
            status="fail",
            errors=("paper FinalVerdict already exists; superseding verdicts require a separate slice",),
            details={"project_root": str(root)},
        )

    current_pipeline_result = validate_paper_pipeline_project(root)
    if not current_pipeline_result.passed:
        return current_pipeline_result

    review_result = validate_paper_independent_review(
        root,
        review_source,
        expected_review_sha256,
        expected_reviewer_id,
    )
    if not review_result.passed:
        return review_result

    review = json.loads(Path(review_source).read_text(encoding="utf-8"))
    governance_dir = root / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    review_path = governance_dir / "INDEPENDENT_REVIEW.json"
    review_path.write_text(
        json.dumps(review, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    gate_path = governance_dir / "REVIEW_GATE.json"
    gate_result = PaperPipelineGateResult(
        status="pass",
        details={
            "review_id": review["REVIEW_RUN_ID"],
            "reviewer_type": review["reviewer_type"],
            "review_source": str(Path(review_source).resolve()),
            "review_artifact": str(review_path),
            "review_sha256": str(expected_review_sha256).lower(),
            "evidence_pack_sha256": review["evidence_pack"]["sha256"],
            "synthetic_only": True,
        },
    )
    write_gate_result(gate_result, gate_path)

    generated_at = datetime.now(timezone.utc).isoformat()
    pipeline_gate_path = root / "evidence" / "PAPER_PIPELINE_GATE.json"
    pack_path = root / "evidence" / "ref-paper-review-pack.zip"
    privacy_path = root / "paper_task" / "PRIVACY_ATTESTATION.yaml"
    verdict = {
        "verdict_id": f"fv-paper-{_safe_review_token(str(review['REVIEW_RUN_ID']))}",
        "produced_by": "devframe-paper-governance-finalizer",
        "produced_at": generated_at,
        "producer_role": "governance",
        "final_state": "accepted_with_limitation",
        "inputs_reviewed": [
            str(root / relative) for relative in _PAPER_REVIEW_EVIDENCE
        ] + [str(review_path)],
        "gate_summary": [
            {
                "gate_id": "paper-pipeline",
                "result": "pass",
                "evidence_path": str(pipeline_gate_path),
            },
            {
                "gate_id": "paper-evidence-pack",
                "result": "pass",
                "evidence_path": str(pack_path),
            },
            {
                "gate_id": "paper-independent-review",
                "result": "pass",
                "evidence_path": str(gate_path),
            },
            {
                "gate_id": "paper-synthetic-boundary",
                "result": "warning",
                "evidence_path": str(privacy_path),
            },
        ],
        "reviewer_summary": {
            "reviewer_id": str(review["REVIEW_RUN_ID"]),
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [
            "dry-run only paper workflow; no real paper final acceptance claimed",
            "synthetic offline candidate; real user paper content was not processed",
            "external provider submission was not executed",
        ],
        "human_or_governance_reference": (
            f"devframe-paper-finalize:{review['REVIEW_RUN_ID']}"
        ),
    }
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(
        json.dumps(verdict, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return PaperPipelineGateResult(
        status="pass",
        details={
            **review_result.details,
            "review_artifact": str(review_path),
            "gate_artifact": str(gate_path),
            "final_verdict": str(final_path),
        },
    )


def _safe_review_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return token or "unknown-review"


def validate_paper_pipeline_project(project_root: str | Path) -> PaperPipelineGateResult:
    root = Path(project_root).resolve()
    errors: list[str] = []
    task_result = validate_paper_task_source(root)
    errors.extend(task_result.errors)

    pack_result = validate_evidence_pack(
        root / "evidence" / "ref-paper-review-pack.zip",
        content_root=root,
    )
    errors.extend(pack_result.errors)

    live_bypass_result = scan_submission_bypass()
    errors.extend(live_bypass_result.errors)

    required_files = (
        root / "review" / "REVIEW_REPORT.md",
        root / "evidence" / "PRE_SUBMISSION_CHECK.yaml",
        root / "evidence" / "BYPASS_CHECK_OUTPUT.txt",
        root / "submission" / "SUBMISSION_RESULT.json",
    )
    for path in required_files:
        if not path.is_file():
            errors.append(f"missing paper pipeline artifact: {path.relative_to(root).as_posix()}")

    pre_submission_path = root / "evidence" / "PRE_SUBMISSION_CHECK.yaml"
    if pre_submission_path.is_file():
        pre_submission = _load_yaml(
            pre_submission_path.read_text(encoding="utf-8"),
            "PRE_SUBMISSION_CHECK.yaml",
            errors,
        )
        if pre_submission.get("result") != "pass":
            errors.append("PRE_SUBMISSION_CHECK.yaml: result must be pass")

    bypass_path = root / "evidence" / "BYPASS_CHECK_OUTPUT.txt"
    bypass_status = "missing"
    if bypass_path.is_file():
        try:
            bypass = json.loads(bypass_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"BYPASS_CHECK_OUTPUT.txt: invalid JSON: {exc}")
            bypass = {}
        bypass_status = str(bypass.get("status", "missing"))
        if bypass_status != "pass":
            errors.append("BYPASS_CHECK_OUTPUT.txt: status must be pass")

    submission_path = root / "submission" / "SUBMISSION_RESULT.json"
    if submission_path.is_file():
        try:
            submission = json.loads(submission_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"SUBMISSION_RESULT.json: invalid JSON: {exc}")
            submission = {}
        if submission.get("mode") != "dry_run":
            errors.append("SUBMISSION_RESULT.json: mode must remain dry_run")
        if submission.get("submitted_to_gpt") is not False:
            errors.append("SUBMISSION_RESULT.json: submitted_to_gpt must be false")
        if submission.get("status") != "dry_run_success":
            errors.append("SUBMISSION_RESULT.json: status must be dry_run_success")

    return PaperPipelineGateResult(
        status="pass" if not errors else "fail",
        errors=tuple(errors),
        details={
            "project_root": str(root),
            "paper_task_gate": task_result.status,
            "evidence_pack_gate": pack_result.status,
            "submission_bypass_gate": bypass_status,
            "live_submission_bypass_gate": live_bypass_result.status,
            "synthetic_only": True,
        },
    )


def write_gate_result(result: PaperPipelineGateResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path
