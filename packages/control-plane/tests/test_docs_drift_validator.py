"""Tests for P1-3: documentation drift validator.

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

from pathlib import Path

import pytest

from control_plane.docs_drift_validator import (
    ValidationResult,
    build_docs_drift_payload,
    validate_docs_drift,
    derive_docs_drift,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload(disk_files=None, inventory_entries=None,
             reviewer_index_entries=None, active_plan_files=None,
             docs_readme_entries=None):
    return {
        "disk_files": disk_files or [],
        "inventory_entries": inventory_entries or [],
        "reviewer_index_entries": reviewer_index_entries or [],
        "active_plan_files": active_plan_files or [],
        "docs_readme_entries": docs_readme_entries or [],
    }


# ---------------------------------------------------------------------------
# validate_docs_drift
# ---------------------------------------------------------------------------

class TestValidateDocsDrift:
    def test_empty_passes(self):
        result = validate_docs_drift(_payload())
        assert result.valid

    def test_all_disk_files_in_inventory_passes(self):
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md", "evidence-x.md"],
            inventory_entries=["plan-a.md", "evidence-x.md", "old-stage.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md"],
            docs_readme_entries=["plan-a.md"],
        ))
        assert result.valid

    def test_disk_file_missing_from_inventory_fails(self):
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md", "unlisted.md"],
            inventory_entries=["plan-a.md"],
        ))
        assert not result.valid
        assert any("unlisted.md" in e and "inventory" in e for e in result.errors)

    def test_active_plan_missing_from_reviewer_index_fails(self):
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md", "plan-b.md"],
            inventory_entries=["plan-a.md", "plan-b.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md", "plan-b.md"],
        ))
        assert not result.valid
        assert any("plan-b.md" in e and "reviewer-index" in e for e in result.errors)

    def test_active_plan_not_in_disk_files_is_consistency_error(self):
        """If active_plan_files references a file not on disk, that's a
        consistency error — the caller provided inconsistent data."""
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md"],
            inventory_entries=["plan-a.md", "ghost.md"],
            reviewer_index_entries=["ghost.md"],
            active_plan_files=["ghost.md"],
        ))
        assert not result.valid
        assert any("ghost.md" in e and "disk" in e for e in result.errors)

    def test_historical_file_missing_from_reviewer_index_ok(self):
        """Historical files are NOT required in reviewer-index — only active
        plans need reviewer visibility."""
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md", "old-stage-3.md"],
            inventory_entries=["plan-a.md", "old-stage-3.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md"],
            docs_readme_entries=["plan-a.md"],
        ))
        assert result.valid

    def test_historical_file_missing_from_inventory_still_fails(self):
        """Even historical files must appear in inventory — every disk file
        must be inventoried."""
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md", "old-stage-3.md"],
            inventory_entries=["plan-a.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md"],
        ))
        assert not result.valid
        assert any("old-stage-3.md" in e for e in result.errors)

    def test_multiple_errors_accumulated(self):
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md", "unlisted-1.md", "unlisted-2.md"],
            inventory_entries=["plan-a.md"],
            reviewer_index_entries=[],
            active_plan_files=["plan-a.md", "unlisted-1.md"],
        ))
        assert not result.valid
        # unlisted-1: inventory + reviewer-index, unlisted-2: inventory, plan-a: reviewer-index
        assert len(result.errors) >= 3

    def test_reviewer_index_extra_entries_not_an_error(self):
        """Having extra entries in reviewer-index beyond active plans is fine —
        the index may list more than just active plans."""
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md"],
            inventory_entries=["plan-a.md"],
            reviewer_index_entries=["plan-a.md", "extra-ref.md"],
            active_plan_files=["plan-a.md"],
            docs_readme_entries=["plan-a.md"],
        ))
        assert result.valid

    def test_inventory_extra_entries_not_an_error(self):
        """Inventory may list files that no longer exist on disk (historical
        traceability)."""
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md"],
            inventory_entries=["plan-a.md", "retired-plan.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md"],
            docs_readme_entries=["plan-a.md"],
        ))
        assert result.valid

    def test_deferred_module_missing_from_reviewer_index_fails(self):
        """Deferred modules are 'master-plan companion docs' — they affect
        the roadmap and should appear in reviewer-index."""
        result = validate_docs_drift(_payload(
            disk_files=["deferred-x.md"],
            inventory_entries=["deferred-x.md"],
            reviewer_index_entries=[],
            active_plan_files=["deferred-x.md"],
        ))
        assert not result.valid
        assert any("deferred-x.md" in e for e in result.errors)

    def test_evidence_record_missing_from_inventory_fails(self):
        """Evidence records must appear in inventory — adding without
        visibility is a failure."""
        result = validate_docs_drift(_payload(
            disk_files=["evidence-run-20260706.md"],
            inventory_entries=[],
        ))
        assert not result.valid
        assert any("evidence-run-20260706.md" in e for e in result.errors)

    def test_active_plan_missing_from_readme_fails(self):
        """Active plan docs must appear in docs/README.md — per P1-3 spec
        line 202."""
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md"],
            inventory_entries=["plan-a.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md"],
            docs_readme_entries=[],
        ))
        assert not result.valid
        assert any("plan-a.md" in e and "README" in e for e in result.errors)

    def test_historical_file_not_in_readme_is_ok(self):
        """Historical files are NOT required in docs/README.md — only active
        plans / master-plan companion docs."""
        result = validate_docs_drift(_payload(
            disk_files=["plan-a.md", "old-stage-3.md"],
            inventory_entries=["plan-a.md", "old-stage-3.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md"],
            docs_readme_entries=["plan-a.md"],
        ))
        assert result.valid


    def test_current_repo_docs_status_inventory_is_visible(self):
        """Real public-doc path: current docs/status files must be inventoried."""
        payload = build_docs_drift_payload(REPO_ROOT)
        result = validate_docs_drift(payload)
        assert result.valid, "\n".join(result.errors)
        assert "review-governance-kernel-completion-20260706.md" in payload["disk_files"]
        assert "review-governance-kernel-completion-20260706.md" in (
            payload["inventory_entries"]
        )


# ---------------------------------------------------------------------------
# derive_docs_drift
# ---------------------------------------------------------------------------

class TestDeriveDocsDrift:
    def test_empty_packet(self):
        result = derive_docs_drift(_payload())
        assert result["disk_count"] == 0
        assert result["untracked_count"] == 0
        assert result["missing_from_reviewer_index_count"] == 0

    def test_all_clean(self):
        result = derive_docs_drift(_payload(
            disk_files=["a.md", "b.md"],
            inventory_entries=["a.md", "b.md"],
            reviewer_index_entries=["a.md"],
            active_plan_files=["a.md"],
        ))
        assert result["disk_count"] == 2
        assert result["untracked_count"] == 0
        assert result["missing_from_reviewer_index_count"] == 0

    def test_counts_untracked(self):
        result = derive_docs_drift(_payload(
            disk_files=["a.md", "orphan.md"],
            inventory_entries=["a.md"],
        ))
        assert result["untracked_count"] == 1
        assert "orphan.md" in result["untracked"]

    def test_counts_missing_from_reviewer_index(self):
        result = derive_docs_drift(_payload(
            disk_files=["a.md", "b.md"],
            inventory_entries=["a.md", "b.md"],
            reviewer_index_entries=["a.md"],
            active_plan_files=["a.md", "b.md"],
        ))
        assert result["missing_from_reviewer_index_count"] == 1
        assert "b.md" in result["missing_from_reviewer_index"]

    def test_projection_is_read_only(self):
        pkt = _payload(
            disk_files=["a.md"],
            inventory_entries=["a.md"],
        )
        original = {"disk_files": list(pkt["disk_files"])}
        derive_docs_drift(pkt)
        assert pkt["disk_files"] == original["disk_files"]

    def test_projection_reports_active_plan_not_on_disk(self):
        """P0 fix: projection must detect active plan not on disk —
        same as validator."""
        result = derive_docs_drift(_payload(
            disk_files=["plan-a.md"],
            inventory_entries=["plan-a.md", "ghost.md"],
            reviewer_index_entries=["ghost.md"],
            active_plan_files=["ghost.md"],
            docs_readme_entries=[],
        ))
        assert not result["valid"]
        assert result["active_not_on_disk_count"] == 1
        assert "ghost.md" in result["active_not_on_disk"]
        assert any("disk" in e for e in result["errors"])

    def test_projection_reports_missing_from_readme(self):
        """Projection must report active plans missing from docs/README.md."""
        result = derive_docs_drift(_payload(
            disk_files=["plan-a.md"],
            inventory_entries=["plan-a.md"],
            reviewer_index_entries=["plan-a.md"],
            active_plan_files=["plan-a.md"],
            docs_readme_entries=[],
        ))
        assert not result["valid"]
        assert result["missing_from_readme_count"] == 1
        assert "plan-a.md" in result["missing_from_readme"]

    def test_projection_valid_when_all_clean(self):
        """Full clean projection: valid=true, no errors."""
        result = derive_docs_drift(_payload(
            disk_files=["a.md", "b.md"],
            inventory_entries=["a.md", "b.md", "old.md"],
            reviewer_index_entries=["a.md"],
            active_plan_files=["a.md"],
            docs_readme_entries=["a.md"],
        ))
        assert result["valid"]
        assert result["errors"] == []
        assert result["disk_count"] == 2
        assert result["untracked_count"] == 0
        assert result["missing_from_reviewer_index_count"] == 0
        assert result["missing_from_readme_count"] == 0
        assert result["active_not_on_disk_count"] == 0
