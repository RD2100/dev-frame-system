#!/usr/bin/env python3
"""Local review evidence pack helper.

This tool only prepares local evidence packs. It never submits to GPT, opens a
browser, connects to CDP, or decides whether a review is accepted.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


SELF_REFERENTIAL_FILES = frozenset(
    {
        "PACK_MANIFEST.md",
        "PACK_MANIFEST_VERIFY.md",
        "VALIDATION_RESULT.json",
        "OUTPUT_DIRECTORY_TREE.md",
    }
)
EXCLUSION_TEXT = "hash intentionally excluded for self-referential verification artifact"
TRUE_VALUES = {"yes", "true"}
FALSE_VALUES = {"no", "false"}


def sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_self_referential(path: Path) -> bool:
    return path.name in SELF_REFERENTIAL_FILES


def relative_name(report_dir: Path, path: Path) -> str:
    return path.relative_to(report_dir).as_posix()


def read_text_fallback(path: Path) -> str:
    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def parse_bool_token(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    return None


def normalize_route_key(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip()).strip("_").lower()


def build_default_route(review_run_id: str) -> dict:
    return {
        "review_submitted": False,
        "review_run_id": review_run_id,
        "overall_judgment": "pending",
        "full_broader_real_chain_testing_unblocked": False,
        "production_promotion_approved": False,
        "hardcoded_driver_replacement_approved": False,
        "guard_removal_approved": False,
        "evidence_cleanup_approved": False,
        "human_required": False,
    }


def build_evidence_skeleton(task_id: str, review_run_id: str) -> dict[str, str]:
    route = json.dumps(build_default_route(review_run_id), indent=2, ensure_ascii=False) + "\n"
    return {
        "TASKSPEC.md": "\n".join(
            [
                "# TaskSpec",
                "",
                f"REVIEW_RUN_ID: {review_run_id}",
                "",
                "## Scope",
                "",
                f"Task ID: {task_id}",
                "",
                "Fill in the approved scope, success criteria, and stage-specific boundaries here.",
                "",
            ]
        ),
        "READ_SET.json": json.dumps({"review_run_id": review_run_id, "reads": [], "read_outside_allowed_scope": False}, indent=2, ensure_ascii=False) + "\n",
        "WRITE_SET.json": json.dumps(
            {"review_run_id": review_run_id, "writes": [], "changed_files": [], "write_outside_allowed_scope": False},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        "TEST_OUTPUT.md": "\n".join(
            [
                "# Test Output Summary",
                "",
                f"REVIEW_RUN_ID: {review_run_id}",
                "",
                "```text",
                "Record verification commands, exit codes, and key summary lines here.",
                "```",
                "",
            ]
        ),
        "TEST_EXIT_CODES.txt": "",
        "SAFETY_CHECK.md": "\n".join(
            [
                "# Safety Check",
                "",
                f"REVIEW_RUN_ID: {review_run_id}",
                "",
                "```text",
                "allowed_files_only: pending",
                "broader_real_chain_testing_unblocked: no",
                "production_promotion_executed: no",
                "hardcoded_driver_replaced: no",
                "guard_removed: no",
                "evidence_cleanup_executed: no",
                "```",
                "",
            ]
        ),
        "COMMAND_LOG.md": "\n".join(
            [
                "# Command Log",
                "",
                f"REVIEW_RUN_ID: {review_run_id}",
                "",
                "| Step | Command / Action | Result |",
                "|---|---|---|",
                "| 1 | Fill in stage-specific actions | pending |",
                "",
            ]
        ),
        "GPT_REVIEW_PROMPT.md": "\n".join(
            [
                "# GPT Review Prompt",
                "",
                f"REVIEW_RUN_ID: {review_run_id}",
                "",
                "Fill in the stage-specific GPT review request and required decision fields here.",
                "",
            ]
        ),
        "POST_REVIEW_ROUTE.json": route,
    }


def build_supplement_note(review_run_id: str, supplement_items: list[str]) -> str:
    if not supplement_items:
        raise ValueError("supplement_items must not be empty")
    lines = [
        "# Supplement Note",
        "",
        f"REVIEW_RUN_ID: {review_run_id}",
        "",
        "This is a supplemented evidence pack.",
        "",
        "Supplemented items:",
        "",
        "```text",
    ]
    lines.extend(supplement_items)
    lines.extend(["```", ""])
    return "\n".join(lines)


def build_workspace_scope_explanation(review_run_id: str, scope_inputs: dict) -> str:
    required_keys = {
        "before_file",
        "after_file",
        "diff_file",
        "preexisting_scope_note",
        "allowed_changed_files",
        "evidence_sources",
    }
    missing = sorted(key for key in required_keys if key not in scope_inputs or not scope_inputs[key])
    if missing:
        raise ValueError(f"missing workspace scope inputs: {', '.join(missing)}")
    allowed_changed_files = scope_inputs["allowed_changed_files"]
    evidence_sources = scope_inputs["evidence_sources"]
    if not isinstance(allowed_changed_files, list) or not allowed_changed_files:
        raise ValueError("allowed_changed_files must be a non-empty list")
    if not isinstance(evidence_sources, list) or not evidence_sources:
        raise ValueError("evidence_sources must be a non-empty list")

    lines = [
        "# Workspace Scope Explanation",
        "",
        f"REVIEW_RUN_ID: {review_run_id}",
        "",
        "## Snapshot Files",
        "",
        "```text",
        f"before: {scope_inputs['before_file']}",
        f"after: {scope_inputs['after_file']}",
        f"diff: {scope_inputs['diff_file']}",
        "```",
        "",
        "## Pre-existing Scope Note",
        "",
        scope_inputs["preexisting_scope_note"],
        "",
        "## Allowed Changed Files",
        "",
        "```text",
    ]
    lines.extend(allowed_changed_files)
    lines.extend(["```", "", "## Supporting Evidence", "", "```text"])
    lines.extend(evidence_sources)
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_supplement_pack(report_dir: Path, review_run_id: str, supplement_inputs: dict) -> list[Path]:
    supplement_items = supplement_inputs.get("supplement_items")
    workspace_scope = supplement_inputs.get("workspace_scope")
    if not isinstance(supplement_items, list) or not supplement_items:
        raise ValueError("supplement_items must be a non-empty list")
    if not isinstance(workspace_scope, dict):
        raise ValueError("workspace_scope must be an object")

    note_path = report_dir / "SUPPLEMENT_NOTE.md"
    scope_path = report_dir / "WORKSPACE_SCOPE_EXPLANATION.md"
    ensure_within_directory(report_dir, note_path)
    ensure_within_directory(report_dir, scope_path)
    note_path.write_text(build_supplement_note(review_run_id, supplement_items), encoding="utf-8")
    scope_path.write_text(build_workspace_scope_explanation(review_run_id, workspace_scope), encoding="utf-8")
    return [note_path, scope_path]


def read_workspace_status_lines(workspace_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(workspace_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"git status failed with exit code {result.returncode}"
        raise RuntimeError(message)
    return result.stdout.splitlines()


def ensure_within_directory(parent: Path, child: Path) -> None:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    if parent_resolved != child_resolved and parent_resolved not in child_resolved.parents:
        raise ValueError(f"path escapes report directory: {child}")


def workspace_status_path(report_dir: Path, snapshot_name: str) -> Path:
    allowed = {
        "before": "WORKSPACE_STATUS_BEFORE.txt",
        "after": "WORKSPACE_STATUS_AFTER.txt",
        "diff": "WORKSPACE_STATUS_DIFF.txt",
    }
    if snapshot_name not in allowed:
        raise ValueError(f"unsupported snapshot name: {snapshot_name}")
    path = report_dir / allowed[snapshot_name]
    ensure_within_directory(report_dir, path)
    return path


def write_workspace_status_snapshot(
    report_dir: Path,
    snapshot_name: str,
    workspace_root: Path | None = None,
    status_lines: list[str] | None = None,
) -> Path:
    path = workspace_status_path(report_dir, snapshot_name)
    if snapshot_name == "diff":
        raise ValueError("use write_workspace_status_diff() for diff snapshots")
    lines = status_lines if status_lines is not None else read_workspace_status_lines(workspace_root or Path.cwd())
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return path


def write_workspace_status_diff(report_dir: Path, before_lines: list[str] | None = None, after_lines: list[str] | None = None) -> Path:
    before_path = workspace_status_path(report_dir, "before")
    after_path = workspace_status_path(report_dir, "after")
    diff_path = workspace_status_path(report_dir, "diff")
    if before_lines is None:
        before_lines = read_text_fallback(before_path).splitlines() if before_path.exists() else []
    if after_lines is None:
        after_lines = read_text_fallback(after_path).splitlines() if after_path.exists() else []
    diff_text = "\n".join(
        difflib.unified_diff(before_lines, after_lines, fromfile=before_path.name, tofile=after_path.name, lineterm="")
    )
    if diff_text:
        diff_text += "\n"
    diff_path.write_text(diff_text, encoding="utf-8")
    return diff_path


def capture_workspace_status(report_dir: Path, snapshot_name: str, workspace_root: Path | None = None) -> list[Path]:
    if snapshot_name not in {"before", "after", "diff"}:
        raise ValueError(f"unsupported workspace status capture target: {snapshot_name}")
    if snapshot_name == "before":
        return [write_workspace_status_snapshot(report_dir, "before", workspace_root=workspace_root)]
    if snapshot_name == "after":
        after_path = write_workspace_status_snapshot(report_dir, "after", workspace_root=workspace_root)
        paths = [after_path]
        if workspace_status_path(report_dir, "before").exists():
            paths.append(write_workspace_status_diff(report_dir))
        return paths
    return [write_workspace_status_diff(report_dir)]


def write_evidence_skeleton(report_dir: Path, task_id: str, review_run_id: str, overwrite: bool = False) -> list[Path]:
    skeleton = build_evidence_skeleton(task_id, review_run_id)
    existing = [report_dir / name for name in skeleton if (report_dir / name).exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"skeleton target already exists: {names}")

    created: list[Path] = []
    for name, content in skeleton.items():
        path = report_dir / name
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return created


def extract_yaml_block(text: str) -> list[str]:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "YAML":
            start = idx + 1
            break
    else:
        return []

    yaml_lines: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if yaml_lines and indent == 0 and stripped and ":" not in stripped:
            break
        if stripped or yaml_lines:
            yaml_lines.append(line.rstrip())
    return yaml_lines


def parse_yaml_like_block(lines: list[str]) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        if ":" not in stripped:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if value:
            current[key] = value
        else:
            child: dict = {}
            current[key] = child
            stack.append((indent, child))
    return root


def load_review_decision(captured_review_path: Path, expected_review_run_id: str) -> tuple[str, dict]:
    text = captured_review_path.read_text(encoding="utf-8")
    expected_line = f"REVIEW_RUN_ID: {expected_review_run_id}"
    if expected_line not in text:
        raise ValueError(f"expected exact review run id line not found: {expected_line}")

    block = extract_yaml_block(text)
    if not block:
        raise ValueError("yaml decision block not found in captured review")

    parsed = parse_yaml_like_block(block)
    actual_run_id = str(parsed.get("REVIEW_RUN_ID", "")).strip()
    if actual_run_id and actual_run_id != expected_review_run_id:
        raise ValueError(f"review run id mismatch: expected {expected_review_run_id}, got {actual_run_id}")
    parsed["REVIEW_RUN_ID"] = expected_review_run_id
    return text, parsed


def build_post_review_route(decision: dict) -> dict:
    route = {
        "review_submitted": True,
        "review_run_id": decision.get("REVIEW_RUN_ID", ""),
        "overall_judgment": str(decision.get("overall_judgment", "pending")).strip() or "pending",
        "full_broader_real_chain_testing_unblocked": False,
        "production_promotion_approved": False,
        "hardcoded_driver_replacement_approved": False,
        "guard_removal_approved": False,
        "evidence_cleanup_approved": False,
        "human_required": False,
    }

    human_required = parse_bool_token(str(decision.get("human_required", "")).strip())
    if human_required is not None:
        route["human_required"] = human_required

    def apply_section(prefix: str, section: dict) -> None:
        route_key = normalize_route_key(prefix)
        accepted = parse_bool_token(str(section.get("accepted", "")).strip()) if "accepted" in section else None
        approved = parse_bool_token(str(section.get("approved", "")).strip()) if "approved" in section else None
        unblocked = parse_bool_token(str(section.get("unblocked", "")).strip()) if "unblocked" in section else None
        status = str(section.get("status", "")).strip()
        if accepted is not None:
            route[f"{route_key}_accepted"] = accepted
        if approved is not None:
            route[f"{route_key}_approved"] = approved
        if prefix == "broader_real_chain_testing":
            route["full_broader_real_chain_testing_unblocked"] = bool(unblocked) if unblocked is not None else False
            if status:
                route["broader_real_chain_testing_status"] = status
        elif unblocked is not None:
            route[f"{route_key}_unblocked"] = unblocked
            if status:
                route[f"{route_key}_status"] = status

        for child_key, child_value in section.items():
            if child_key in {"accepted", "approved", "unblocked", "status"}:
                continue
            if isinstance(child_value, dict):
                apply_section(f"{prefix}_{child_key}", child_value)
                continue
            child_bool = parse_bool_token(str(child_value).strip())
            if child_bool is not None:
                route[f"{route_key}_{normalize_route_key(child_key)}"] = child_bool
            elif str(child_value).strip():
                route[f"{route_key}_{normalize_route_key(child_key)}"] = str(child_value).strip()

    for key, value in decision.items():
        if key in {"REVIEW_RUN_ID", "overall_judgment", "human_required"}:
            continue
        route_key = normalize_route_key(key)
        if isinstance(value, dict):
            apply_section(key, value)
        else:
            scalar_bool = parse_bool_token(str(value).strip())
            if scalar_bool is not None:
                route[route_key] = scalar_bool
    return route


def decision_to_markdown(decision: dict) -> str:
    lines = ["# GPT Review Decision", "", f"REVIEW_RUN_ID: {decision.get('REVIEW_RUN_ID', '')}", "", "```yaml"]
    for key, value in decision.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for child_key, child_value in value.items():
                lines.append(f"  {child_key}: {child_value}")
        else:
            lines.append(f"{key}: {value}")
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_post_review_route(report_dir: Path, route: dict) -> Path:
    path = report_dir / "POST_REVIEW_ROUTE.json"
    path.write_text(json.dumps(route, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def persist_review_result(
    report_dir: Path,
    task_id: str,
    review_run_id: str,
    captured_review_path: Path,
    zip_name: str | None,
    do_zip: bool,
) -> dict:
    _, decision = load_review_decision(captured_review_path, review_run_id)
    route = build_post_review_route(decision)

    result_path = report_dir / "GPT_REVIEW_RESULT.md"
    decision_path = report_dir / "GPT_REVIEW_DECISION.md"
    shutil.copyfile(captured_review_path, result_path)
    decision_path.write_text(decision_to_markdown(decision), encoding="utf-8")
    write_post_review_route(report_dir, route)

    validation = run_flow(report_dir, task_id, review_run_id, zip_name, do_zip)
    validation["post_review_route"] = route
    return validation


def iter_pack_files(report_dir: Path, zip_name: str | None = None):
    for path in sorted(report_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".zip":
            continue
        if zip_name and path.name == zip_name:
            continue
        yield path


def expected_pack_entry_names(report_dir: Path, zip_name: str | None = None) -> list[str]:
    names = [relative_name(report_dir, path) for path in iter_pack_files(report_dir, zip_name)]
    if "PACK_MANIFEST.md" not in names:
        names.append("PACK_MANIFEST.md")
    return sorted(names)


def generate_manifest(report_dir: Path, task_id: str, review_run_id: str, zip_name: str | None = None) -> Path:
    rows: list[tuple[str, str]] = []
    for name in expected_pack_entry_names(report_dir, zip_name):
        path = report_dir / name
        digest = EXCLUSION_TEXT if is_self_referential(path) else sha256_hex(path)
        rows.append((name, digest))

    lines = [
        "# Pack Manifest",
        "",
        f"Task ID: {task_id}",
        f"Review Run ID: {review_run_id}",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "| File | SHA256 |",
        "|---|---|",
    ]
    lines.extend(f"| {name} | {digest} |" for name, digest in rows)

    manifest_path = report_dir / "PACK_MANIFEST.md"
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path


def create_zip(report_dir: Path, zip_name: str) -> Path:
    zip_path = report_dir / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in iter_pack_files(report_dir, zip_name):
            archive.write(path, relative_name(report_dir, path))
    return zip_path


def parse_manifest(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("| File |"):
            in_table = True
            continue
        if not in_table or stripped == "|---|---|" or not stripped.startswith("|"):
            continue
        parts = [part.strip() for part in stripped.split("|")]
        if len(parts) >= 3 and parts[1]:
            result[parts[1]] = parts[2]
    return result


def zip_entries(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path, "r") as archive:
        return {info.filename for info in archive.infolist() if not info.is_dir()}


def validate_pack(report_dir: Path, task_id: str, review_run_id: str, zip_name: str | None = None) -> dict:
    manifest_path = report_dir / "PACK_MANIFEST.md"
    manifest_files = parse_manifest(manifest_path) if manifest_path.exists() else {}
    expected_names = expected_pack_entry_names(report_dir, zip_name)

    hash_failures: list[str] = []
    hash_exclusions: list[str] = []
    for name, expected in manifest_files.items():
        path = report_dir / name
        if expected == EXCLUSION_TEXT:
            hash_exclusions.append(name)
            continue
        if not path.exists():
            continue
        actual = sha256_hex(path)
        if actual != expected:
            hash_failures.append(f"{name} (manifest={expected[:12]}..., actual={actual[:12]}...)")

    zip_exists = False
    zip_entry_count = 0
    missing_from_zip: list[str] = []
    extra_in_zip: list[str] = []
    if zip_name:
        zip_path = report_dir / zip_name
        zip_exists = zip_path.exists()
        if zip_exists:
            entries = zip_entries(zip_path)
            zip_entry_count = len(entries)
            manifest_names = set(expected_names)
            missing_from_zip = sorted(manifest_names - entries)
            extra_in_zip = sorted(entries - manifest_names)

    passed = (
        not hash_failures
        and not missing_from_zip
        and not extra_in_zip
        and (not zip_name or zip_exists)
    )
    return {
        "review_run_id": review_run_id,
        "task_id": task_id,
        "validation_scope": "evidence_pack_integrity",
        "stage_status": "passed" if passed else "failed",
        "zip_exists": zip_exists,
        "zip_entry_count": zip_entry_count,
        "manifest_file_count": len(expected_names),
        "missing_from_zip": missing_from_zip,
        "extra_in_zip": extra_in_zip,
        "hash_failures": hash_failures,
        "hash_exclusions": hash_exclusions,
        "validation_verdict": "passed" if passed else "failed",
    }


def verify_manifest_zip_consistency(
    report_dir: Path,
    zip_name: str | None = None,
    manifest_name: str = "PACK_MANIFEST.md",
) -> dict:
    """Cross-check manifest entries against zip entries and file hashes.

    Returns a structured result suitable for inclusion in validation reports.
    """
    zip_path = report_dir / zip_name if zip_name else None
    manifest_path = report_dir / manifest_name

    # --- Read manifest entries ---
    manifest_entries = parse_manifest(manifest_path) if manifest_path.exists() else {}
    # --- Read zip entries ---
    zip_names: set[str] = set()
    if zip_path and zip_path.exists():
        zip_names = zip_entries(zip_path)
    # --- Hash verification: compare manifest against zip entry bytes ---
    hash_mismatches: list[str] = []
    verified: list[str] = []
    _zip_bytes: dict[str, bytes] = {}
    if zip_path and zip_path.exists():
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                _zip_bytes[info.filename] = zf.read(info.filename)

    def _hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    for name, expected_hash in sorted(manifest_entries.items()):
        if expected_hash == EXCLUSION_TEXT:
            continue
        if name not in _zip_bytes:
            hash_mismatches.append(f"{name}: entry not found in zip")
            continue
        actual = _hash_bytes(_zip_bytes[name])
        if actual != expected_hash:
            hash_mismatches.append(f"{name}: hash mismatch (expected={expected_hash[:12]}..., actual={actual[:12]}...)")
        else:
            verified.append(name)

    # --- Cross-reference ---
    manifest_names = set(manifest_entries.keys())
    # Files in manifest but NOT in zip
    manifest_only = sorted(manifest_names - zip_names)
    # Files in zip but NOT in manifest
    zip_only = sorted(zip_names - manifest_names)
    # Files in both
    in_both = sorted(manifest_names & zip_names)

    passed = not hash_mismatches and not manifest_only and not zip_only
    return {
        "consistency_verdict": "passed" if passed else "failed",
        "manifest_file_count": len(manifest_entries),
        "zip_entry_count": len(zip_names),
        "files_in_both": len(in_both),
        "manifest_only": manifest_only,
        "zip_only": zip_only,
        "hash_mismatches": hash_mismatches,
        "hash_verified": len(verified),
        "hash_excluded": len(manifest_entries) - len(verified) - len(hash_mismatches),
    }


def write_validation(report_dir: Path, result: dict) -> Path:
    path = report_dir / "VALIDATION_RESULT.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_manifest_verify(report_dir: Path, result: dict) -> Path:
    path = report_dir / "PACK_MANIFEST_VERIFY.md"
    verdict = result.get("validation_verdict", "unknown")
    lines = [
        "# Pack Manifest Verify",
        "",
        f"REVIEW_RUN_ID: {result.get('review_run_id', '')}",
        "",
        "Manifest verification completed with `tools/review_pack_flow.py`.",
        "",
        "```text",
        f"zip_exists: {str(result.get('zip_exists', False)).lower()}",
        f"zip_entry_count: {result.get('zip_entry_count', 0)}",
        f"manifest_file_count: {result.get('manifest_file_count', 0)}",
        f"missing_from_zip: {json.dumps(result.get('missing_from_zip', []), ensure_ascii=False)}",
        f"extra_in_zip: {json.dumps(result.get('extra_in_zip', []), ensure_ascii=False)}",
        f"hash_failures: {json.dumps(result.get('hash_failures', []), ensure_ascii=False)}",
        f"validation_verdict: {verdict}",
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_summary(result: dict) -> None:
    verdict = result.get("validation_verdict", "unknown").upper()
    alignment_ok = not result.get("missing_from_zip") and not result.get("extra_in_zip")
    hashes_ok = not result.get("hash_failures")
    lines = [
        f"Review Pack Flow - {verdict}",
        f"  Task: {result.get('task_id', '?')}",
        f"  Run: {result.get('review_run_id', '?')}",
        f"  Zip: {'PASS' if result.get('zip_exists') else 'N/A'} (entries={result.get('zip_entry_count', 0)})",
        f"  Hashes: {'PASS' if hashes_ok else 'FAIL'}",
        f"  Manifest-Zip Alignment: {'PASS' if alignment_ok else 'FAIL'}",
    ]
    if result.get("hash_failures"):
        lines.append(f"  Hash Failures: {', '.join(result['hash_failures'])}")
    if result.get("missing_from_zip"):
        lines.append(f"  Missing from zip: {', '.join(result['missing_from_zip'])}")
    if result.get("extra_in_zip"):
        lines.append(f"  Extra in zip: {', '.join(result['extra_in_zip'])}")
    print("\n".join(lines))


def run_flow(report_dir: Path, task_id: str, review_run_id: str, zip_name: str | None, do_zip: bool) -> dict:
    generate_manifest(report_dir, task_id, review_run_id, zip_name)
    if do_zip and zip_name:
        create_zip(report_dir, zip_name)

    result = validate_pack(report_dir, task_id, review_run_id, zip_name if do_zip else None)
    write_validation(report_dir, result)
    write_manifest_verify(report_dir, result)

    if do_zip and zip_name:
        generate_manifest(report_dir, task_id, review_run_id, zip_name)
        create_zip(report_dir, zip_name)
        result = validate_pack(report_dir, task_id, review_run_id, zip_name)
        write_validation(report_dir, result)
        write_manifest_verify(report_dir, result)

    # Post-generation manifest-zip consistency cross-check
    if do_zip and zip_name:
        consistency = verify_manifest_zip_consistency(report_dir, zip_name=zip_name)
        result["manifest_zip_consistency"] = consistency
        if consistency["consistency_verdict"] == "failed":
            result["stage_status"] = "failed"
            result["validation_verdict"] = "failed"
        write_validation(report_dir, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate manifest, zip, and validation for a review evidence pack.")
    parser.add_argument("report_dir", help="Path to the report/evidence directory")
    parser.add_argument("task_id", help="Task identifier for the pack")
    parser.add_argument("review_run_id", help="Review run identifier")
    parser.add_argument("--zip-out", default=None, help="Zip archive name (default: <review_run_id>.zip)")
    parser.add_argument("--no-zip", action="store_true", help="Skip zip archive creation")
    parser.add_argument("--no-validate", action="store_true", help="Skip validation step")
    parser.add_argument("--json", action="store_true", help="Output validation result as JSON to stdout")
    parser.add_argument("--init-skeleton", action="store_true", help="Create a conservative evidence skeleton in the report directory")
    parser.add_argument("--overwrite-existing", action="store_true", help="Allow skeleton generation to overwrite existing files")
    parser.add_argument(
        "--capture-workspace-status",
        choices=["before", "after", "diff"],
        default=None,
        help="Write local workspace status snapshot artifacts into the report directory",
    )
    parser.add_argument(
        "--write-supplement-pack",
        default=None,
        help="JSON file with explicit supplement_items and workspace_scope inputs",
    )
    parser.add_argument(
        "--persist-review",
        default=None,
        help="Captured GPT review markdown file to persist into the report directory before validation",
    )
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    if not report_dir.is_dir():
        print(f"ERROR: report_dir not found: {report_dir}", file=sys.stderr)
        return 2

    zip_name = args.zip_out or f"{args.review_run_id}.zip"
    do_zip = not args.no_zip

    if args.init_skeleton:
        try:
            created = write_evidence_skeleton(report_dir, args.task_id, args.review_run_id, overwrite=args.overwrite_existing)
        except FileExistsError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"[skeleton] wrote {len(created)} files")

    if args.capture_workspace_status:
        try:
            paths = capture_workspace_status(report_dir, args.capture_workspace_status, workspace_root=Path.cwd())
        except (RuntimeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"[workspace-status] wrote {', '.join(path.name for path in paths)}")

    if args.write_supplement_pack:
        supplement_path = Path(args.write_supplement_pack)
        if not supplement_path.is_file():
            print(f"ERROR: supplement input not found: {supplement_path}", file=sys.stderr)
            return 2
        try:
            supplement_inputs = json.loads(read_text_fallback(supplement_path))
            written = write_supplement_pack(report_dir, args.review_run_id, supplement_inputs)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"[supplement-pack] wrote {', '.join(path.name for path in written)}")

    if args.persist_review:
        captured_review_path = Path(args.persist_review)
        if not captured_review_path.is_file():
            print(f"ERROR: captured review not found: {captured_review_path}", file=sys.stderr)
            return 2
        result = persist_review_result(report_dir, args.task_id, args.review_run_id, captured_review_path, zip_name, do_zip)
        print(f"[review] {report_dir / 'GPT_REVIEW_RESULT.md'}")
        print(f"[decision] {report_dir / 'GPT_REVIEW_DECISION.md'}")
        print(f"[route] {report_dir / 'POST_REVIEW_ROUTE.json'}")
        print(f"[validate] {report_dir / 'VALIDATION_RESULT.json'}")
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print()
            print_summary(result)
        return 0 if result["validation_verdict"] == "passed" else 1

    generate_manifest(report_dir, args.task_id, args.review_run_id, zip_name)
    print(f"[manifest] {report_dir / 'PACK_MANIFEST.md'}")

    if do_zip:
        zip_path = create_zip(report_dir, zip_name)
        print(f"[zip] {zip_path} ({zip_path.stat().st_size} bytes)")
    else:
        print("[zip] skipped (--no-zip)")

    if args.no_validate:
        print("[validate] skipped (--no-validate)")
        return 0

    result = run_flow(report_dir, args.task_id, args.review_run_id, zip_name, do_zip)
    print(f"[validate] {report_dir / 'VALIDATION_RESULT.json'}")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print()
        print_summary(result)
    return 0 if result["validation_verdict"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
