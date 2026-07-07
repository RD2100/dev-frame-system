"""P1-3: documentation drift validator.

Per design-coverage-gap-remediation-plan.md:194-212:

  1. Verify every docs/status/*.md file appears in status-document-inventory.md.
  2. Check that master-plan companion docs appear in reviewer-index.md
     when they affect implementation.
  3. Keep warnings targeted; do not require docs/README.md to list every
     historical status file.

Acceptance:
  - adding a public subsystem, evidence record, or deferred module without
    inventory/reviewer visibility fails a local check or produces a clear
    warning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


_STATUS_DOC_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\.md")


def _extract_markdown_filenames(text: str) -> set[str]:
    """Return markdown basenames referenced in public docs."""
    return {Path(match.group(0)).name for match in _STATUS_DOC_PATTERN.finditer(text)}


def _extract_inventory_state_files(text: str, states: set[str]) -> set[str]:
    """Extract filenames from the status inventory classification table."""
    files: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        state = cells[0].strip("`")
        if state in states:
            files.update(_extract_markdown_filenames(cells[1]))
    return files


def build_docs_drift_payload(repo_root: str | Path) -> dict:
    """Build a docs drift payload from this repository's public docs.

    This is the real repo-path entrypoint for the P1-3 drift check. It keeps
    the validator pure while letting tests and gates exercise the actual
    docs/status inventory, docs/README.md, and reviewer index files.
    """
    root = Path(repo_root)
    status_dir = root / "docs" / "status"
    inventory_path = status_dir / "status-document-inventory.md"
    reviewer_index_path = status_dir / "reviewer-index.md"
    docs_readme_path = root / "docs" / "README.md"

    disk_files = {
        path.name for path in status_dir.glob("*.md") if path.is_file()
    }
    inventory_text = inventory_path.read_text(encoding="utf-8-sig")
    reviewer_index_text = reviewer_index_path.read_text(encoding="utf-8-sig")
    docs_readme_text = docs_readme_path.read_text(encoding="utf-8-sig")

    return {
        "disk_files": sorted(disk_files),
        "inventory_entries": sorted(_extract_markdown_filenames(inventory_text)),
        "reviewer_index_entries": sorted(
            _extract_markdown_filenames(reviewer_index_text)
        ),
        "active_plan_files": sorted(
            _extract_inventory_state_files(
                inventory_text,
                {"active-plan", "deferred-module-plan"},
            )
        ),
        "docs_readme_entries": sorted(_extract_markdown_filenames(docs_readme_text)),
    }


def _check_consistency(
    disk_files: set[str],
    inventory_entries: set[str],
    active_plan_files: set[str],
    reviewer_index_entries: set[str],
    docs_readme_entries: set[str],
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Shared drift-check logic used by both validator and projection."""
    errors: list[str] = []

    # (1) Every disk file must appear in inventory.
    missing_from_inventory = disk_files - inventory_entries
    for f in sorted(missing_from_inventory):
        if collect_errors:
            errors.append(
                f"docs_drift: {f!r} exists on disk but is missing from "
                f"status-document-inventory.md"
            )
        else:
            return False, errors

    # (2) Active plan files referencing something not on disk is inconsistent.
    active_not_on_disk = active_plan_files - disk_files
    for f in sorted(active_not_on_disk):
        if collect_errors:
            errors.append(
                f"docs_drift: {f!r} listed as active_plan but not found on disk "
                f"(inconsistent caller data)"
            )
        else:
            return False, errors

    # (3) Active plan files must appear in docs/README.md.
    #     Only master-plan companion docs — NOT every historical file.
    missing_from_readme = active_plan_files - docs_readme_entries
    for f in sorted(missing_from_readme):
        if collect_errors:
            errors.append(
                f"docs_drift: {f!r} is an active-plan / master-plan companion "
                f"doc but is missing from docs/README.md"
            )
        else:
            return False, errors

    # (4) Active plan files must appear in reviewer-index.
    missing_from_reviewer = active_plan_files - reviewer_index_entries
    for f in sorted(missing_from_reviewer):
        if collect_errors:
            errors.append(
                f"docs_drift: {f!r} is an active-plan / master-plan companion "
                f"doc but is missing from reviewer-index.md"
            )
        else:
            return False, errors

    return True, errors


def validate_docs_drift(payload: dict) -> ValidationResult:
    """Validate documentation consistency.

    payload keys:
      - disk_files: list[str] — all docs/status/*.md filenames on disk
      - inventory_entries: list[str] — filenames appearing in inventory
      - reviewer_index_entries: list[str] — filenames in reviewer-index
      - active_plan_files: list[str] — active-plan / master-plan companion
        filenames that MUST appear in reviewer-index
    """
    errors: list[str] = []

    disk_files = set(payload.get("disk_files") or [])
    inventory_entries = set(payload.get("inventory_entries") or [])
    reviewer_index_entries = set(payload.get("reviewer_index_entries") or [])
    active_plan_files = set(payload.get("active_plan_files") or [])
    docs_readme_entries = set(payload.get("docs_readme_entries") or [])

    _, drift_errors = _check_consistency(
        disk_files, inventory_entries, active_plan_files,
        reviewer_index_entries, docs_readme_entries,
        collect_errors=True,
    )
    errors.extend(drift_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_docs_drift(payload: dict) -> dict:
    """Read-only projection: uses shared _check_consistency() so projection
    cannot report clean when validator would fail.

    Returns derived counts plus all drift errors (pass-through from the
    shared check, same as validator sees).
    """
    disk_files = set(payload.get("disk_files") or [])
    inventory_entries = set(payload.get("inventory_entries") or [])
    reviewer_index_entries = set(payload.get("reviewer_index_entries") or [])
    active_plan_files = set(payload.get("active_plan_files") or [])
    docs_readme_entries = set(payload.get("docs_readme_entries") or [])

    valid, consistency_errors = _check_consistency(
        disk_files, inventory_entries, active_plan_files,
        reviewer_index_entries, docs_readme_entries,
        collect_errors=True,
    )

    valid = len(consistency_errors) == 0

    untracked = sorted(disk_files - inventory_entries)
    missing_from_reviewer = sorted(active_plan_files - reviewer_index_entries)
    missing_from_readme = sorted(active_plan_files - docs_readme_entries)
    active_not_on_disk = sorted(active_plan_files - disk_files)

    return {
        "disk_count": len(disk_files),
        "valid": valid,
        "errors": consistency_errors,
        "untracked_count": len(untracked),
        "untracked": untracked,
        "missing_from_reviewer_index_count": len(missing_from_reviewer),
        "missing_from_reviewer_index": missing_from_reviewer,
        "missing_from_readme_count": len(missing_from_readme),
        "missing_from_readme": missing_from_readme,
        "active_not_on_disk_count": len(active_not_on_disk),
        "active_not_on_disk": active_not_on_disk,
    }
