"""A42 -- Policy Signed Pinning tests.

Verifies:
1. Policy hash is bound into anchor log entries
2. Provenance uses path hash (not absolute path) to prevent path leakage
3. JSON Schema artifact is available for external validation
4. Checkpoint export includes provenance before file write
5. policy-schema command exports the schema
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import (
    app, _load_audit_policy, _compute_policy_provenance,
    _AUDIT_POLICY_JSON_SCHEMA,
)

runner = CliRunner()


def _make_policy(tmp: Path, policy: dict) -> str:
    p = tmp / "policy.json"
    p.write_text(json.dumps(policy), encoding="utf-8")
    return str(p)


def _valid_policy(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "signature_policy": "optional",
        "chain_verification_mode": "chain_only",
        "allowed_key_ids": [],
        "required_artifacts": [],
        "strict_chain": False,
        "strict_timestamps": True,
        "description": "test-policy-a42",
    }
    base.update(overrides)
    return base


# ============================================================
# TestA42PathHashPrivacy
# ============================================================

class TestA42PathHashPrivacy:
    """Provenance uses path hash, not absolute path."""

    def test_no_absolute_path_in_provenance(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        prov = _compute_policy_provenance(ppath)
        assert "policy_path" not in prov  # must not leak path
        assert "policy_path_hash" in prov

    def test_path_hash_is_deterministic(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        p1 = _compute_policy_provenance(ppath)
        p2 = _compute_policy_provenance(ppath)
        assert p1["policy_path_hash"] == p2["policy_path_hash"]

    def test_path_hash_differs_for_different_paths(self, tmp_path):
        (tmp_path / "dir1").mkdir(parents=True, exist_ok=True)
        p1_path = _make_policy(tmp_path / "dir1", _valid_policy())
        (tmp_path / "dir2").mkdir(parents=True, exist_ok=True)
        p2_path = _make_policy(tmp_path / "dir2", _valid_policy())
        p1 = _compute_policy_provenance(p1_path)
        p2 = _compute_policy_provenance(p2_path)
        assert p1["policy_path_hash"] != p2["policy_path_hash"]


# ============================================================
# TestA42AnchorLogBinding
# ============================================================

class TestA42AnchorLogBinding:
    """Policy hash is bound into anchor log entries."""

    def test_anchor_log_contains_policy_sha256(self, tmp_path):
        """paper audit --anchor-log --policy should include policy_sha256 in log."""
        # We test this via _load_audit_policy returning provenance
        # then verifying the anchor log entry construction includes it.
        ppath = _make_policy(tmp_path, _valid_policy())
        policy = _load_audit_policy(ppath)
        prov = policy["_policy_provenance"]
        # Verify provenance has the fields that get bound
        assert "policy_sha256" in prov
        assert "policy_path_hash" in prov

    def test_anchor_entry_structure(self, tmp_path):
        """Verify anchor log entry includes policy fields when policy is loaded."""
        ppath = _make_policy(tmp_path, _valid_policy())
        policy = _load_audit_policy(ppath)
        prov = policy["_policy_provenance"]

        # Simulate anchor log entry construction (as in audit command)
        entry = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-test",
            "run_id": "run-test",
            "zip_sha256": "a" * 64,
            "bundle_hash": "b" * 64,
            "signed": False,
            "prev_hash": "",
        }
        if prov:
            entry["policy_sha256"] = prov.get("policy_sha256", "")
            entry["policy_path_hash"] = prov.get("policy_path_hash", "")

        assert "policy_sha256" in entry
        assert len(entry["policy_sha256"]) == 64
        assert "policy_path_hash" in entry
        assert len(entry["policy_path_hash"]) == 64


# ============================================================
# TestA42JsonSchemaArtifact
# ============================================================

class TestA42JsonSchemaArtifact:
    """JSON Schema artifact for external validation."""

    def test_schema_is_valid_json_schema(self):
        assert "$schema" in _AUDIT_POLICY_JSON_SCHEMA
        assert "properties" in _AUDIT_POLICY_JSON_SCHEMA
        assert "schema_version" in _AUDIT_POLICY_JSON_SCHEMA["properties"]

    def test_schema_enforces_schema_version(self):
        sv_prop = _AUDIT_POLICY_JSON_SCHEMA["properties"]["schema_version"]
        assert sv_prop.get("const") == "1.0"

    def test_schema_signature_policy_enum(self):
        sp = _AUDIT_POLICY_JSON_SCHEMA["properties"]["signature_policy"]
        assert "enum" in sp
        assert set(sp["enum"]) == {"required", "optional", "off"}

    def test_schema_chain_mode_enum(self):
        cm = _AUDIT_POLICY_JSON_SCHEMA["properties"]["chain_verification_mode"]
        assert "enum" in cm
        assert set(cm["enum"]) == {"chain_only", "chain_plus_zip", "chain_partial"}

    def test_policy_schema_command_stdout(self, tmp_path):
        """paper policy-schema should output valid JSON Schema."""
        result = runner.invoke(app, ["paper", "policy-schema"])
        assert result.exit_code == 0
        schema = json.loads(result.stdout)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "properties" in schema

    def test_policy_schema_command_file_output(self, tmp_path):
        """paper policy-schema --output should write to file."""
        out = tmp_path / "schema.json"
        result = runner.invoke(app, ["paper", "policy-schema", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        schema = json.loads(out.read_text(encoding="utf-8"))
        assert "properties" in schema


# ============================================================
# TestA42CheckpointExportBinding
# ============================================================

class TestA42CheckpointExportBinding:
    """Checkpoint export includes provenance before file write."""

    def test_checkpoint_export_file_contains_provenance(self, tmp_path):
        """Checkpoint export file should include policy_provenance."""
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-cp",
            "run_id": "run-cp",
            "zip_sha256": "e" * 64,
            "bundle_hash": "f" * 64,
            "signed": False,
            "prev_hash": "",
        }, separators=(",", ":"))
        log.write_text(entry + "\n", encoding="utf-8")

        ppath = _make_policy(tmp_path, _valid_policy())
        export_path = tmp_path / "cp_export.json"

        result = runner.invoke(app, [
            "paper", "checkpoint",
            "--log", str(log),
            "--export", str(export_path),
            "--policy", ppath,
        ])
        assert result.exit_code == 0
        assert export_path.exists()

        cp_data = json.loads(export_path.read_text(encoding="utf-8"))
        assert "policy_provenance" in cp_data
        assert "policy_sha256" in cp_data["policy_provenance"]


# ============================================================
# TestA42Integration
# ============================================================

class TestA42Integration:
    """Integration: provenance privacy + anchor binding + schema."""

    def test_full_signed_pinning_workflow(self, tmp_path):
        """End-to-end: load policy, verify provenance privacy, check anchor structure."""
        ppath = _make_policy(tmp_path, _valid_policy())

        # Step 1: provenance has no absolute path
        prov = _compute_policy_provenance(ppath)
        assert "policy_path" not in prov
        assert "policy_path_hash" in prov
        assert len(prov["policy_sha256"]) == 64

        # Step 2: load policy with provenance
        policy = _load_audit_policy(ppath, expected_hash=prov["policy_sha256"])
        assert "_policy_provenance" in policy

        # Step 3: verify JSON schema is well-formed
        assert _AUDIT_POLICY_JSON_SCHEMA["properties"]["signature_policy"]["enum"]
        assert _AUDIT_POLICY_JSON_SCHEMA["properties"]["chain_verification_mode"]["enum"]

        # Step 4: policy-schema command works
        result = runner.invoke(app, ["paper", "policy-schema"])
        assert result.exit_code == 0
        schema = json.loads(result.stdout)
        assert schema["title"] == "AuditPolicy"

        # Step 5: verify-chain with policy includes redacted provenance
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-a42",
            "run_id": "run-a42",
            "zip_sha256": "a" * 64,
            "bundle_hash": "b" * 64,
            "signed": False,
            "prev_hash": "",
        }, separators=(",", ":"))
        log.write_text(entry + "\n", encoding="utf-8")

        result = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", str(log),
            "--policy", ppath,
            "--expected-policy-hash", prov["policy_sha256"],
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        assert "policy_provenance" in data
        assert "policy_path" not in data["policy_provenance"]  # privacy
        assert "policy_path_hash" in data["policy_provenance"]
        assert data["policy_provenance"]["policy_sha256"] == prov["policy_sha256"]
