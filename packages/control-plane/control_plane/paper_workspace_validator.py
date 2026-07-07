"""P3-1: paper KB workspace contract validator.

Per design-coverage-gap-remediation-plan.md:299-316:

  - paper workspace facts are represented through existing governance objects;
  - Paper KB cannot bypass evidence or local decisions;
  - block whole-vault scans, path traversal, source-root-equals-vault-root,
    and unaudited Obsidian writeback;
  - keep scheduler, browser submission, PDF conversion, and skill extraction
    out of the first Paper KB slice.

Repair strategy:
  1. Define paper workspace entry schema.
  2. Block dangerous operations (vault scan, traversal, unaudited writeback).
  3. Block out-of-scope operations (scheduler, browser, PDF, skill extraction).
  4. Require audit trail for any write/export.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

# Operations that are explicitly forbidden in the first Paper KB slice.
FORBIDDEN_OPERATIONS: tuple[str, ...] = (
    "scheduler",
    "browser_submission",
    "pdf_conversion",
    "skill_extraction",
)

# Operations that require an audit trail (write/export side effects).
WRITE_OPERATIONS: tuple[str, ...] = (
    "write",
    "export",
    "sync",
    "publish",
    "transform",
)

# Recognized operation types.
KNOWN_OPERATIONS: tuple[str, ...] = (
    "read",
    "write",
    "export",
    "sync",
    "publish",
    "transform",
    "list",
    "search",
    "scheduler",
    "browser_submission",
    "pdf_conversion",
    "skill_extraction",
)

# Path patterns that indicate traversal or escape.
TRAVERSAL_PATTERNS: tuple[str, ...] = ("../", "..\\")


def _has_traversal(path: str) -> bool:
    """True when any path segment equals '..'."""
    normalized = path.replace("\\", "/")
    return any(part == ".." for part in normalized.split("/"))


def _is_absolute_path(path: str) -> bool:
    """True for POSIX, UNC, or drive-qualified absolute paths."""
    normalized = path.replace("\\", "/").strip()
    return (
        posixpath.isabs(normalized)
        or (len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":")
    )


def _normalize_path_for_boundary(path: str) -> str:
    """Normalize a path for equality comparison — resolves '.', ' .. ' aliases."""
    normalized = path.replace("\\", "/").strip()
    normalized = posixpath.normpath(normalized)
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def _is_strict_subpath(path: str, parent: str) -> bool:
    """True when path is normalized under parent, but not equal to parent."""
    if path == parent:
        return False
    try:
        return posixpath.commonpath([parent, path]) == parent
    except ValueError:
        return False


def _is_subpath_or_same(path: str, parent: str) -> bool:
    """True when path is normalized under parent or exactly parent."""
    return path == parent or _is_strict_subpath(path, parent)


def _scope_stays_within_boundary(scope: str, boundary: str) -> bool:
    """Resolve relative scope under boundary and confirm it cannot escape."""
    normalized_boundary = _normalize_path_for_boundary(boundary)
    normalized_scope = _normalize_path_for_boundary(scope)
    candidate = _normalize_path_for_boundary(
        posixpath.join(normalized_boundary, normalized_scope)
    )
    return _is_subpath_or_same(candidate, normalized_boundary)


# Operations that are only safe with explicit scope boundaries.
SCOPED_OPERATIONS: tuple[str, ...] = (
    "read",
    "write",
    "export",
    "sync",
    "publish",
    "transform",
    "search",
)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _is_valid_paper_entry_shape(
    entry: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Structural check — required fields, known values, path sanity."""
    errors: list[str] = []
    eid = str(entry.get("id", "")).strip()
    prefix = f"paper_entry[{eid or '<missing>'}]"

    for field in ("id", "workspace_path", "operation"):
        raw = entry.get(field, "")
        if isinstance(raw, str):
            raw = raw.strip()
        if not raw:
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    operation = entry.get("operation", "")
    if operation not in KNOWN_OPERATIONS:
        if collect_errors:
            errors.append(
                f"{prefix}: operation={operation!r} is not a known operation; "
                f"must be one of {KNOWN_OPERATIONS}"
            )
        else:
            return False, errors

    return True, errors


def _check_paper_boundary_rules(
    entry: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Boundary rule checks — what a paper workspace entry must NOT do."""
    errors: list[str] = []
    eid = entry.get("id", "")
    prefix = f"paper_entry[{eid or '<missing>'}]"
    operation = str(entry.get("operation", "")).strip()
    scope = str(entry.get("scope", "")).strip()
    workspace_path = str(entry.get("workspace_path", "")).strip()
    source_root = str(entry.get("source_root", "")).strip()
    audit_trail = str(entry.get("audit_trail", "")).strip()

    # Block forbidden operations.
    if operation in FORBIDDEN_OPERATIONS:
        if collect_errors:
            errors.append(
                f"{prefix}: operation={operation!r} is forbidden in the first "
                f"Paper KB slice; {FORBIDDEN_OPERATIONS} are out of scope"
            )
        else:
            return False, errors

    # Block whole-vault scans — scope must be explicit for scoped operations.
    if operation in SCOPED_OPERATIONS and not scope:
        if collect_errors:
            errors.append(
                f"{prefix}: operation={operation!r} requires explicit scope; "
                f"whole-vault scans are blocked"
            )
        else:
            return False, errors

    # Block path traversal in scope.
    if scope and _has_traversal(scope):
        if collect_errors:
            errors.append(
                f"{prefix}: scope={scope!r} contains path traversal; "
                f"parent-directory segments are blocked"
            )
        else:
            return False, errors

    # Block absolute scope paths; scopes must remain relative to the paper root.
    if scope and _is_absolute_path(scope):
        if collect_errors:
            errors.append(
                f"{prefix}: scope={scope!r} is an absolute path; "
                f"scope must be relative to workspace_path or source_root"
            )
        else:
            return False, errors

    # Block path traversal in workspace_path.
    if workspace_path and _has_traversal(workspace_path):
        if collect_errors:
            errors.append(
                f"{prefix}: workspace_path={workspace_path!r} contains "
                f"path traversal; parent-directory segments are blocked"
            )
        else:
            return False, errors

    # Block path traversal in source_root.
    if source_root and _has_traversal(source_root):
        if collect_errors:
            errors.append(
                f"{prefix}: source_root={source_root!r} contains path "
                f"traversal; parent-directory segments are blocked"
            )
        else:
            return False, errors

    # Block source-root-equals-vault-root (with path normalization).
    if source_root and workspace_path:
        normalized_source_root = _normalize_path_for_boundary(source_root)
        normalized_workspace_path = _normalize_path_for_boundary(workspace_path)
        if normalized_source_root == normalized_workspace_path:
            if collect_errors:
                errors.append(
                    f"{prefix}: source_root equals workspace_path "
                    f"(after normalization); "
                    f"source root must be a subdirectory, not the entire vault"
                )
            else:
                return False, errors
        elif not _is_strict_subpath(normalized_source_root, normalized_workspace_path):
            if collect_errors:
                errors.append(
                    f"{prefix}: source_root={source_root!r} escapes "
                    f"workspace_path={workspace_path!r} after normalization; "
                    f"source root must remain within workspace_path"
                )
            else:
                return False, errors

    # Resolve relative scope against configured roots to catch boundary escapes.
    scope_boundaries = tuple(
        boundary for boundary in (source_root, workspace_path) if boundary
    )
    for boundary in scope_boundaries:
        if scope and not _scope_stays_within_boundary(scope, boundary):
            if collect_errors:
                errors.append(
                    f"{prefix}: scope={scope!r} escapes boundary={boundary!r} "
                    f"after normalization"
                )
            else:
                return False, errors

    # Block unaudited Obsidian writeback — write operations need audit_trail.
    if operation in WRITE_OPERATIONS and not audit_trail:
        if collect_errors:
            errors.append(
                f"{prefix}: operation={operation!r} requires audit_trail; "
                f"unaudited Obsidian writeback is blocked"
            )
        else:
            return False, errors

    return True, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_paper_workspace(payload: dict) -> ValidationResult:
    """Validate paper workspace entries against boundary rules.

    Enforces:
      - Forbidden operations are rejected
      - Whole-vault scans are blocked
      - Path traversal is blocked
      - Source root cannot equal vault root
      - Unaundited writeback is blocked
    """
    errors: list[str] = []
    entries: list[dict] = payload.get("paper_entries") or []

    for entry in entries:
        _, shape_errors = _is_valid_paper_entry_shape(entry, collect_errors=True)
        errors.extend(shape_errors)
        _, boundary_errors = _check_paper_boundary_rules(entry, collect_errors=True)
        errors.extend(boundary_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_paper_workspace(payload: dict) -> dict:
    """Read-only projection of paper workspace usage.

    Returns counts by operation and scope status.
    Shape-invalid entries are excluded.
    """
    entries: list[dict] = payload.get("paper_entries") or []

    total = 0
    by_operation: dict[str, int] = {}
    scoped_count = 0
    write_count = 0
    audited_write_count = 0

    for entry in entries:
        shape_ok, _ = _is_valid_paper_entry_shape(entry, collect_errors=False)
        if not shape_ok:
            continue

        total += 1
        operation = str(entry.get("operation", "")).strip()
        scope = str(entry.get("scope", "")).strip()
        audit_trail = str(entry.get("audit_trail", "")).strip()

        by_operation[operation] = by_operation.get(operation, 0) + 1

        if scope:
            scoped_count += 1

        if operation in WRITE_OPERATIONS:
            write_count += 1
            if audit_trail:
                audited_write_count += 1

    return {
        "total_entries": total,
        "scoped_count": scoped_count,
        "write_count": write_count,
        "audited_write_count": audited_write_count,
        "by_operation": by_operation,
    }
