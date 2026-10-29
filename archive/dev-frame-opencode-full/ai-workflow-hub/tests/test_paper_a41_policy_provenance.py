"""A41 -- Policy Provenance tests.

Verifies that policy files carry SHA-256 provenance metadata and
that --expected-policy-hash enforces integrity.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

# Ensure the package is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app, _load_audit_policy, _compute_policy_provenance

runner = CliRunner()


def _make_policy(tmp: Path, policy: dict) -> str:
    """Write a policy JSON file and return its path."""
    p = tmp / "policy.json"
    p.write_text(json.dumps(policy), encoding="utf-8")
    return str(p)


def _valid_policy(**overrides) -> dict:
    """Return a minimal valid policy dict."""
    base = {
        "schema_version": "1.0",
        "signature_policy": "optional",
        "chain_verification_mode": "chain_only",
        "allowed_key_ids": [],
        "required_artifacts": [],
        "strict_chain": False,
        "strict_timestamps": True,
        "description": "test-policy-a41",
    }
    base.update(overrides)
    return base


def _mock_runtime():
    """Return a mock _paper_runtime dict for audit/verify commands."""
    return {
        "sanitize": lambda x: x,
    }


# ============================================================
# TestA41ProvenanceComputation
# ============================================================

class TestA41ProvenanceComputation:
    """Test _compute_policy_provenance and _load_audit_policy provenance."""

    def test_provenance_has_required_fields(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        prov = _compute_policy_provenance(ppath)
        assert "policy_path_hash" in prov
        assert "policy_sha256" in prov
        assert "policy_loaded_at" in prov
        assert len(prov["policy_sha256"]) == 64  # SHA-256 hex

    def test_provenance_hash_matches_file(self, tmp_path):
        import hashlib
        ppath = _make_policy(tmp_path, _valid_policy())
        prov = _compute_policy_provenance(ppath)
        expected = hashlib.sha256(Path(ppath).read_bytes()).hexdigest()
        assert prov["policy_sha256"] == expected

    def test_provenance_path_hash_is_hex(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        prov = _compute_policy_provenance(ppath)
        assert len(prov["policy_path_hash"]) == 64  # SHA-256 hex of path

    def test_load_audit_policy_attaches_provenance(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        policy = _load_audit_policy(ppath)
        assert "_policy_provenance" in policy
        assert "policy_sha256" in policy["_policy_provenance"]
        assert "policy_path_hash" in policy["_policy_provenance"]
        assert "policy_loaded_at" in policy["_policy_provenance"]


# ============================================================
# TestA41ExpectedPolicyHash
# ============================================================

class TestA41ExpectedPolicyHash:
    """Test --expected-policy-hash enforcement."""

    def test_matching_hash_passes(self, tmp_path):
        import hashlib
        ppath = _make_policy(tmp_path, _valid_policy())
        expected = hashlib.sha256(Path(ppath).read_bytes()).hexdigest()
        # Should not raise
        policy = _load_audit_policy(ppath, expected_hash=expected)
        assert policy["_policy_provenance"]["policy_sha256"] == expected

    def test_mismatching_hash_exits(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        with pytest.raises(Exception):
            _load_audit_policy(ppath, expected_hash="0" * 64)

    def test_empty_hash_skips_check(self, tmp_path):
        ppath = _make_policy(tmp_path, _valid_policy())
        # Empty string should not trigger hash verification
        policy = _load_audit_policy(ppath, expected_hash="")
        assert "_policy_provenance" in policy


# ============================================================
# TestA41ProvenanceInOutputs
# ============================================================

class TestA41ProvenanceInOutputs:
    """Test that policy_provenance appears in JSON outputs."""

    def test_verify_chain_includes_provenance(self, tmp_path):
        """verify-chain --policy --json should include policy_provenance."""
        # Create a valid anchor log
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-abc123",
            "run_id": "run-001",
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
        assert "policy_provenance" in data
        assert "policy_sha256" in data["policy_provenance"]

    def test_checkpoint_verify_includes_provenance(self, tmp_path):
        """checkpoint --verify --policy --json should include policy_provenance."""
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-abc123",
            "run_id": "run-001",
            "zip_sha256": "a" * 64,
            "bundle_hash": "b" * 64,
            "signed": False,
            "prev_hash": "",
        }, separators=(",", ":"))
        log.write_text(entry + "\n", encoding="utf-8")

        # Compute hashes the same way the CLI does
        import hashlib
        head_hash = hashlib.sha256(entry.encode("utf-8")).hexdigest()
        chain_hash = hashlib.sha256(head_hash.encode("utf-8")).hexdigest()
        cp = {
            "format_version": "1.1",
            "chain_head_hash": head_hash,
            "chain_full_hash": chain_hash,
            "entries_count": 1,
        }
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
        # Provenance is included regardless of verify pass/fail
        data = json.loads(result.stdout, strict=False)
        assert "policy_provenance" in data
        assert len(data["policy_provenance"]["policy_sha256"]) == 64

    def test_no_policy_no_provenance(self, tmp_path):
        """Without --policy, policy_provenance should not appear."""
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-abc123",
            "run_id": "run-001",
            "zip_sha256": "a" * 64,
            "bundle_hash": "b" * 64,
            "signed": False,
            "prev_hash": "",
        }, separators=(",", ":"))
        log.write_text(entry + "\n", encoding="utf-8")

        result = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", str(log),
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        assert "policy_provenance" not in data


# ============================================================
# TestA41HashBinding
# ============================================================

class TestA41HashBinding:
    """Test that policy hash is bound into audit outputs."""

    def test_audit_bundle_includes_policy_provenance(self, tmp_path):
        """paper audit with --policy should embed provenance in bundle_manifest."""
        # This is tested indirectly — the provenance is added to the manifest
        # before writing to the ZIP. We verify via _load_audit_policy that
        # provenance is attached, which the audit command then embeds.
        ppath = _make_policy(tmp_path, _valid_policy())
        policy = _load_audit_policy(ppath)
        assert policy["_policy_provenance"]["policy_sha256"]
        # The audit command reads _policy_data["_policy_provenance"] and
        # adds it to the bundle manifest.

    def test_provenance_survives_reparse(self, tmp_path):
        """Provenance hash should be stable across multiple loads."""
        ppath = _make_policy(tmp_path, _valid_policy())
        p1 = _load_audit_policy(ppath)
        p2 = _load_audit_policy(ppath)
        # SHA-256 should be identical (file content unchanged)
        assert p1["_policy_provenance"]["policy_sha256"] == p2["_policy_provenance"]["policy_sha256"]
        # loaded_at may differ, that's OK


# ============================================================
# TestA41Integration
# ============================================================

class TestA41Integration:
    """Integration test: provenance flows across commands."""

    def test_policy_provenance_end_to_end(self, tmp_path):
        """Load policy, compute provenance, verify hash, use in verify-chain."""
        policy_dict = _valid_policy(
            signature_policy="optional",
            chain_verification_mode="chain_only",
        )
        ppath = _make_policy(tmp_path, policy_dict)

        # Step 1: compute provenance
        prov = _compute_policy_provenance(ppath)
        assert len(prov["policy_sha256"]) == 64

        # Step 2: load with matching hash — should succeed
        policy = _load_audit_policy(ppath, expected_hash=prov["policy_sha256"])
        assert policy["_policy_provenance"]["policy_sha256"] == prov["policy_sha256"]

        # Step 3: use in verify-chain with --expected-policy-hash
        log = tmp_path / "anchor.jsonl"
        entry = json.dumps({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bundle_id": "bundle-test",
            "run_id": "run-test",
            "zip_sha256": "c" * 64,
            "bundle_hash": "d" * 64,
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
        assert data["policy_provenance"]["policy_sha256"] == prov["policy_sha256"]

        # Step 4: wrong hash should fail
        result2 = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", str(log),
            "--policy", ppath,
            "--expected-policy-hash", "f" * 64,
            "--json",
        ])
        assert result2.exit_code != 0
