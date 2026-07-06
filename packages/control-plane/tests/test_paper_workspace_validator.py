"""Tests for P3-1: paper KB workspace contract validator.

Per design-coverage-gap-remediation-plan.md:299-316:
  - block whole-vault scans, path traversal, source-root-equals-vault-root,
    and unaudited Obsidian writeback;
  - keep scheduler, browser submission, PDF conversion, and skill extraction
    out of the first Paper KB slice;
  - paper workspace facts are represented through existing governance objects;
  - Paper KB cannot bypass evidence or local decisions.
"""
from __future__ import annotations

import pytest

from control_plane.paper_workspace_validator import (
    FORBIDDEN_OPERATIONS,
    KNOWN_OPERATIONS,
    derive_paper_workspace,
    validate_paper_workspace,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(**overrides):
    """Minimal valid paper workspace entry."""
    base = {
        "id": "pw-1",
        "workspace_path": "/vault/projects/foo",
        "operation": "read",
        "scope": "projects/foo/docs/",
        "source_root": "/vault/projects/foo/docs",
    }
    base.update(overrides)
    return base


def _payload(entries=None):
    return {"paper_entries": entries or []}


# ---------------------------------------------------------------------------
# Forbidden operations
# ---------------------------------------------------------------------------


class TestForbiddenOperations:
    def test_scheduler_is_forbidden(self):
        entry = _entry(operation="scheduler")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "scheduler" in result.errors[0].lower()
        assert "forbidden" in result.errors[0].lower()

    def test_browser_submission_is_forbidden(self):
        entry = _entry(operation="browser_submission")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "browser_submission" in result.errors[0]

    def test_pdf_conversion_is_forbidden(self):
        entry = _entry(operation="pdf_conversion")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "pdf_conversion" in result.errors[0]

    def test_skill_extraction_is_forbidden(self):
        entry = _entry(operation="skill_extraction")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "skill_extraction" in result.errors[0]

    def test_all_forbidden_listed(self):
        assert "scheduler" in FORBIDDEN_OPERATIONS
        assert "browser_submission" in FORBIDDEN_OPERATIONS
        assert "pdf_conversion" in FORBIDDEN_OPERATIONS
        assert "skill_extraction" in FORBIDDEN_OPERATIONS


# ---------------------------------------------------------------------------
# Whole-vault scan blocking
# ---------------------------------------------------------------------------


class TestVaultScanBlocking:
    def test_read_without_scope_is_blocked(self):
        """Scoped operations (read, write, export, etc.) need explicit scope."""
        entry = _entry(operation="read", scope="")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "scope" in result.errors[0].lower()

    def test_write_without_scope_is_blocked(self):
        entry = _entry(operation="write", scope="", audit_trail="audit-log-1")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "scope" in result.errors[0].lower()

    def test_list_without_scope_is_ok(self):
        """List is not a scoped operation — it describes inventories."""
        entry = _entry(operation="list", scope="")
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_read_with_scope_is_ok(self):
        entry = _entry(operation="read", scope="projects/foo/docs/")
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_read_with_whitespace_scope_is_blocked(self):
        """Whitespace-only scope bypass is blocked (P0-1)."""
        entry = _entry(operation="read", scope="   ")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "scope" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# Path traversal blocking
# ---------------------------------------------------------------------------


class TestPathTraversalBlocking:
    def test_parent_traversal_in_scope_blocked(self):
        entry = _entry(operation="read", scope="../secrets/")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "traversal" in result.errors[0].lower()

    def test_upward_traversal_in_scope_blocked(self):
        entry = _entry(operation="read", scope="..\\etc\\passwd")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid

    def test_traversal_in_workspace_path_blocked(self):
        entry = _entry(workspace_path="../outside-vault/")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "traversal" in result.errors[0].lower()

    def test_normal_scope_no_traversal_ok(self):
        entry = _entry(scope="projects/foo/docs/archive/")
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_scope_exact_parent_segment_blocked(self):
        """Scope='..' is parent traversal (P0-3)."""
        entry = _entry(operation="read", scope="..")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "traversal" in result.errors[0].lower()

    def test_scope_trailing_parent_segment_blocked(self):
        """Scope='foo/..' is parent traversal (P0-3)."""
        entry = _entry(operation="read", scope="foo/..")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "traversal" in result.errors[0].lower()

    def test_workspace_path_exact_parent_segment_blocked(self):
        """Workspace path='..' is traversal."""
        entry = _entry(workspace_path="..")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "traversal" in result.errors[0].lower()

    def test_workspace_path_trailing_parent_segment_blocked(self):
        """Workspace path='foo/..' is traversal."""
        entry = _entry(workspace_path="foo/..")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "traversal" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# Source-root-equals-vault-root blocking
# ---------------------------------------------------------------------------


class TestSourceRootEqualsVaultRoot:
    def test_source_root_equals_workspace_path_blocked(self):
        entry = _entry(
            workspace_path="/vault/",
            source_root="/vault/",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "source_root" in result.errors[0].lower()

    def test_source_root_subdirectory_of_vault_ok(self):
        entry = _entry(
            workspace_path="/vault/",
            source_root="/vault/projects/foo/docs",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_trailing_slash_diff_ok(self):
        """Trailing slash difference is normalized — same path is still blocked."""
        entry = _entry(
            workspace_path="/vault",
            source_root="/vault/",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid

    def test_source_root_dot_alias_equals_workspace_path_blocked(self):
        """'/vault/.' is semantically the vault root — blocked (P0 Round 3)."""
        entry = _entry(
            workspace_path="/vault",
            source_root="/vault/.",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid

    def test_source_root_parent_alias_equals_workspace_path_blocked(self):
        """'/vault/sub/..' is semantically the vault root — blocked (P0 Round 3)."""
        entry = _entry(
            workspace_path="/vault",
            source_root="/vault/sub/..",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid


# ---------------------------------------------------------------------------
# Unaudited writeback blocking
# ---------------------------------------------------------------------------


class TestUnauditedWriteback:
    def test_write_without_audit_trail_blocked(self):
        entry = _entry(
            operation="write", scope="projects/foo/docs/",
            audit_trail="",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "audit" in result.errors[0].lower()

    def test_write_with_audit_trail_ok(self):
        entry = _entry(
            operation="write", scope="projects/foo/docs/",
            audit_trail="audit-001",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_export_without_audit_trail_blocked(self):
        entry = _entry(
            operation="export", scope="projects/foo/docs/",
            audit_trail="",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "audit" in result.errors[0].lower()

    def test_read_without_audit_trail_ok(self):
        """Read is not a write operation — no audit trail needed."""
        entry = _entry(operation="read", audit_trail="")
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_publish_without_audit_trail_blocked(self):
        entry = _entry(
            operation="publish", scope="projects/foo/docs/",
            audit_trail="",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid

    def test_transform_without_audit_trail_blocked(self):
        entry = _entry(
            operation="transform", scope="projects/foo/docs/",
            audit_trail="",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid

    def test_sync_without_audit_trail_blocked(self):
        entry = _entry(
            operation="sync", scope="projects/foo/docs/",
            audit_trail="",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "audit" in result.errors[0].lower()

    def test_write_with_whitespace_audit_trail_blocked(self):
        """Whitespace-only audit_trail bypass is blocked (P0-2)."""
        entry = _entry(
            operation="write", scope="projects/foo/docs/",
            audit_trail="   ",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "audit" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


class TestRequiredFields:
    def test_missing_id(self):
        entry = _entry(id="")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "id" in result.errors[0]

    def test_whitespace_id_blocked(self):
        """Whitespace-only id is treated as missing (P1)."""
        entry = _entry(id="   ")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "id" in result.errors[0]

    def test_missing_workspace_path(self):
        entry = _entry(workspace_path="")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "workspace_path" in result.errors[0]

    def test_whitespace_workspace_path_blocked(self):
        entry = _entry(workspace_path="   ")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "workspace_path" in result.errors[0]

    def test_missing_operation(self):
        entry = _entry(operation="")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "operation" in result.errors[0]

    def test_invalid_operation(self):
        entry = _entry(operation="compile")
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert "compile" in result.errors[0]


# ---------------------------------------------------------------------------
# Multiple errors collected
# ---------------------------------------------------------------------------


class TestErrorCollection:
    def test_multiple_boundary_violations_collected(self):
        """Collect all errors, not just the first."""
        entry = _entry(
            operation="scheduler",
            scope="../outside/",
            workspace_path="/vault/",
            source_root="/vault/",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert not result.valid
        assert len(result.errors) >= 3

    def test_multiple_entries_collected(self):
        e1 = _entry(id="e1", operation="scheduler")
        e2 = _entry(id="e2", operation="write", scope="", audit_trail="")
        result = validate_paper_workspace(_payload([e1, e2]))
        assert not result.valid
        assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# derive_paper_workspace (projection)
# ---------------------------------------------------------------------------


class TestDerivePaperWorkspace:
    def test_empty_payload(self):
        result = derive_paper_workspace({})
        assert result["total_entries"] == 0
        assert result["write_count"] == 0
        assert result["audited_write_count"] == 0

    def test_counts_by_operation(self):
        entries = [
            _entry(id="e1", operation="read"),
            _entry(id="e2", operation="read"),
            _entry(id="e3", operation="write", audit_trail="audit-1"),
        ]
        result = derive_paper_workspace(_payload(entries))
        assert result["total_entries"] == 3
        assert result["by_operation"]["read"] == 2
        assert result["by_operation"]["write"] == 1
        assert result["write_count"] == 1
        assert result["audited_write_count"] == 1

    def test_scoped_count(self):
        entries = [
            _entry(id="e1", operation="read", scope="foo/"),
            _entry(id="e2", operation="list", scope=""),
        ]
        result = derive_paper_workspace(_payload(entries))
        assert result["scoped_count"] == 1

    def test_unaudited_write_tracked(self):
        entries = [
            _entry(id="e1", operation="write", audit_trail="a1"),
            _entry(id="e2", operation="export", audit_trail=""),
        ]
        result = derive_paper_workspace(_payload(entries))
        assert result["write_count"] == 2
        assert result["audited_write_count"] == 1

    def test_projection_does_not_count_whitespace_audit_as_audited(self):
        """Whitespace-only audit_trail is not a real audit record (P0-2)."""
        entries = [
            _entry(id="e1", operation="write", audit_trail="   ",
                   scope="projects/foo/"),
        ]
        result = derive_paper_workspace(_payload(entries))
        assert result["write_count"] == 1
        assert result["audited_write_count"] == 0

    def test_shape_invalid_excluded(self):
        entries = [_entry(id="")]
        result = derive_paper_workspace(_payload(entries))
        assert result["total_entries"] == 0

    def test_projection_read_only(self):
        result = derive_paper_workspace(_payload([_entry()]))
        assert "errors" not in result
        assert "raw_entries" not in result
        assert "decisions" not in result


# ---------------------------------------------------------------------------
# Good path
# ---------------------------------------------------------------------------


class TestGoodPath:
    def test_simple_read_is_valid(self):
        entry = _entry()
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_audited_write_is_valid(self):
        entry = _entry(
            operation="write", scope="projects/foo/docs/",
            audit_trail="audit-001",
        )
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_valid_list_is_ok(self):
        entry = _entry(operation="list", scope="")
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid

    def test_search_is_scoped(self):
        """Search is scoped — must have scope."""
        entry = _entry(operation="search", scope="projects/foo/")
        result = validate_paper_workspace(_payload([entry]))
        assert result.valid
