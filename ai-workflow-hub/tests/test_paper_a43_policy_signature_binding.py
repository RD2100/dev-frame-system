"""A43 -- Policy Signature Binding tests.

Verifies:
1. JSON outputs use policy_file_hash instead of raw policy_file
2. JSON Schema validation runs during policy loading
3. Schema validation warnings are reported (not blocking)
4. Provenance includes schema_validated and schema_warnings fields
"""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import (
    app, _load_audit_policy, _compute_policy_provenance,
    _AUDIT_POLICY_JSON_SCHEMA,
)

runner = CliRunner()


def _make_policy(tmp: Path, policy: dict, name: str = "policy.json") -> str:
    p = tmp / name
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
        "description": "test-policy-a43",
    }
    base.update(overrides)
    return base


# ============================================================
# TestA43PathRedaction
# ============================================================

class TestA43PathRedaction:
    """JSON outputs use policy_file_hash, not raw policy_file."""

    def test_verify_chain_no_raw_path(self, tmp_path):
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-a43",
            "run_id": "run-a43",
            "zip_sha256": "a" * 64,
            "bundle_hash": "b" * 64,
            "signed": False,
            "prev_hash": "",
        }, separators=(",", ":"))
        log.write_text(entry + "\n", encoding="utf-8")

        ppath = _make_policy(tmp_path, _valid_policy())
        result = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", str(log),
            "--policy", ppath,
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        assert "policy_file" not in data  # no raw path
        assert "policy_file_hash" in data  # hash instead
        assert len(data["policy_file_hash"]) == 64

    def test_checkpoint_no_raw_path(self, tmp_path):
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-a43cp",
            "run_id": "run-a43cp",
            "zip_sha256": "c" * 64,
            "bundle_hash": "d" * 64,
            "signed": False,
            "prev_hash": "",
        }, separators=(",", ":"))
        log.write_text(entry + "\n", encoding="utf-8")

        import hashlib
        head_hash = hashlib.sha256(entry.encode("utf-8")).hexdigest()
        chain_hash = hashlib.sha256(head_hash.encode("utf-8")).hexdigest()
        cp = {"format_version": "1.1", "chain_head_hash": head_hash,
              "chain_full_hash": chain_hash, "entries_count": 1}
        cp_path = tmp_path / "cp.json"
        cp_path.write_text(json.dumps(cp), encoding="utf-8")

        ppath = _make_policy(tmp_path, _valid_policy())
        result = runner.invoke(app, [
            "paper", "checkpoint",
            "--log", str(log),
            "--verify", str(cp_path),
            "--policy", ppath,
            "--json",
        ])
        data = json.loads(result.stdout, strict=False)
        assert "policy_file" not in data
        assert "policy_file_hash" in data


# ============================================================
# TestA43SchemaValidation
# ============================================================

class TestA43SchemaValidation:
    """JSON Schema validation during policy loading."""

    def test_valid_policy_schema_validated(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        policy = _load_audit_policy(ppath)
        prov = policy["_policy_provenance"]
        assert prov["schema_validated"] is True
        assert prov["schema_warnings"] == 0

    def test_bad_type_in_optional_field_warns(self, tmp_path):
        """Wrong type in optional field produces warning, not error."""
        pol = _valid_policy()
        pol["strict_chain"] = "not-a-boolean"  # wrong type
        ppath = _make_policy(tmp_path, pol)
        # Should not exit — warnings only
        policy = _load_audit_policy(ppath)
        assert policy["_policy_provenance"]["schema_validated"] is False
        assert policy["_policy_provenance"]["schema_warnings"] > 0

    def test_json_schema_has_required_fields(self):
        props = _AUDIT_POLICY_JSON_SCHEMA["properties"]
        assert "schema_version" in props
        assert "signature_policy" in props
        assert "chain_verification_mode" in props
        assert "allowed_key_ids" in props
        assert "required_artifacts" in props
        assert "strict_chain" in props
        assert "strict_timestamps" in props


# ============================================================
# TestA43ProvenanceEnrichment
# ============================================================

class TestA43ProvenanceEnrichment:
    """Provenance dict includes schema_validated and schema_warnings."""

    def test_provenance_fields_present(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        prov = _compute_policy_provenance(ppath)
        # Base provenance fields
        assert "policy_sha256" in prov
        assert "policy_path_hash" in prov
        assert "policy_loaded_at" in prov

    def test_schema_metadata_after_load(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        policy = _load_audit_policy(ppath)
        prov = policy["_policy_provenance"]
        # A43 fields
        assert "schema_validated" in prov
        assert "schema_warnings" in prov
        assert isinstance(prov["schema_validated"], bool)
        assert isinstance(prov["schema_warnings"], int)


# ============================================================
# TestA43Integration
# ============================================================

class TestA43Integration:
    """Integration: redaction + schema validation + provenance."""

    def test_full_signature_binding_workflow(self, tmp_path):
        """Load policy, verify schema, check redaction in output."""
        ppath = _make_policy(tmp_path, _valid_policy())

        # Step 1: load and verify schema
        policy = _load_audit_policy(ppath)
        assert policy["_policy_provenance"]["schema_validated"] is True

        # Step 2: verify-chain with policy — check redaction
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-a43i",
            "run_id": "run-a43i",
            "zip_sha256": "e" * 64,
            "bundle_hash": "f" * 64,
            "signed": False,
            "prev_hash": "",
        }, separators=(",", ":"))
        log.write_text(entry + "\n", encoding="utf-8")

        result = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", str(log),
            "--policy", ppath,
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        # No raw path
        assert "policy_file" not in data
        # Hash present
        assert "policy_file_hash" in data
        # Provenance has schema validation status
        assert "policy_provenance" in data
        assert "schema_validated" in data["policy_provenance"]

        # Step 3: policy-schema command still works
        result2 = runner.invoke(app, ["paper", "policy-schema"])
        assert result2.exit_code == 0
        schema = json.loads(result2.stdout)
        assert schema["title"] == "AuditPolicy"
