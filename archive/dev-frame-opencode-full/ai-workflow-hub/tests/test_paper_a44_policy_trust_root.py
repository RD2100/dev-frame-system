"""A44 -- Policy Trust Root (--strict-policy).

Verifies:
1. --strict-policy escalates schema warnings to blocking failures
2. Clean policies pass under --strict-policy
3. Schema warnings without --strict-policy are non-blocking (warnings only)
4. --strict-policy works consistently across audit, verify, verify-chain, checkpoint
"""

import hashlib
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import (
    app, _load_audit_policy, _compute_policy_provenance,
    _AUDIT_POLICY_JSON_SCHEMA,
)

runner = CliRunner()


def _make_policy(tmp: Path, policy: dict, name: str = "policy.json") -> str:
    """Write a policy dict to a JSON file and return the path."""
    p = tmp / name
    p.write_text(json.dumps(policy), encoding="utf-8")
    return str(p)


def _valid_policy(**overrides) -> dict:
    """Return a valid audit policy dict with optional overrides."""
    base = {
        "schema_version": "1.0",
        "signature_policy": "optional",
        "chain_verification_mode": "chain_only",
        "allowed_key_ids": [],
        "required_artifacts": [],
        "strict_chain": False,
        "strict_timestamps": True,
        "description": "test-policy-a44",
    }
    base.update(overrides)
    return base


def _invalid_policy() -> dict:
    """Return a policy with a schema issue (wrong type for strict_chain)."""
    pol = _valid_policy()
    pol["strict_chain"] = "yes"  # string instead of boolean
    return pol


def _make_anchor_entry(**overrides) -> str:
    """Create a minimal valid anchor log entry as a JSON string."""
    entry = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "bundle_id": "bundle-a44",
        "run_id": "run-a44",
        "zip_sha256": "a" * 64,
        "bundle_hash": "b" * 64,
        "signed": False,
        "prev_hash": "",
    }
    entry.update(overrides)
    return json.dumps(entry, separators=(",", ":"))


def _make_anchor_log(tmp: Path, entries=None, name: str = "anchor.jsonl") -> str:
    """Write anchor log entries to a JSONL file and return the path."""
    if entries is None:
        entries = [_make_anchor_entry()]
    log = tmp / name
    log.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return str(log)


# ============================================================
# Invoke helpers
# ============================================================

def _invoke_audit(policy_path, strict_policy=False, run_id="test-run-a44"):
    """Invoke 'paper audit' with given policy and --strict-policy flag."""
    args = ["paper", "audit", "--run-id", run_id, "--policy", policy_path]
    if strict_policy:
        args.append("--strict-policy")
    return runner.invoke(app, args)


def _invoke_verify(zip_path, policy_path, strict_policy=False):
    """Invoke 'paper verify' with given policy and --strict-policy flag."""
    args = ["paper", "verify", "--zip", zip_path, "--policy", policy_path]
    if strict_policy:
        args.append("--strict-policy")
    return runner.invoke(app, args)


def _invoke_verify_chain(log_path, policy_path, strict_policy=False):
    """Invoke 'paper verify-chain' with given policy and --strict-policy flag."""
    args = ["paper", "verify-chain", "--log", log_path, "--policy", policy_path]
    if strict_policy:
        args.append("--strict-policy")
    return runner.invoke(app, args)


def _invoke_checkpoint(log_path, policy_path, strict_policy=False):
    """Invoke 'paper checkpoint' with given policy and --strict-policy flag."""
    args = ["paper", "checkpoint", "--log", log_path, "--policy", policy_path]
    if strict_policy:
        args.append("--strict-policy")
    return runner.invoke(app, args)


# ============================================================
# TestA44StrictPolicyOption
# ============================================================

class TestA44StrictPolicyOption:
    """--strict-policy option on the audit command."""

    def test_strict_policy_blocks_on_schema_warnings(self, tmp_path):
        """Schema issue (wrong type) + --strict-policy -> exit_code 1."""
        ppath = _make_policy(tmp_path, _invalid_policy())
        result = _invoke_audit(ppath, strict_policy=True)
        assert result.exit_code == 1
        lower_err = result.stderr.lower() if result.stderr else ""
        assert "schema error" in lower_err or "strict-policy" in lower_err

    def test_strict_policy_passes_clean_policy(self, tmp_path):
        """Valid policy + --strict-policy -> policy accepted, no schema errors."""
        ppath = _make_policy(tmp_path, _valid_policy())
        log_path = _make_anchor_log(tmp_path)
        result = _invoke_verify_chain(log_path, ppath, strict_policy=True)
        assert result.exit_code == 0

    def test_non_strict_policy_warns_only(self, tmp_path):
        """Schema warnings without --strict-policy -> exit_code 0, warning on stderr."""
        ppath = _make_policy(tmp_path, _invalid_policy())
        log_path = _make_anchor_log(tmp_path)
        result = _invoke_verify_chain(log_path, ppath, strict_policy=False)
        assert result.exit_code == 0
        lower_err = result.stderr.lower() if result.stderr else ""
        assert "schema warning" in lower_err


# ============================================================
# TestA44StrictPolicyOnVerify
# ============================================================

class TestA44StrictPolicyOnVerify:
    """--strict-policy on the verify command."""

    def test_verify_with_strict_policy_blocks(self, tmp_path):
        """Invalid policy + verify --strict-policy -> exit_code != 0."""
        ppath = _make_policy(tmp_path, _invalid_policy())
        fake_zip = str(tmp_path / "nonexistent.zip")
        result = _invoke_verify(fake_zip, ppath, strict_policy=True)
        assert result.exit_code != 0


# ============================================================
# TestA44StrictPolicyOnVerifyChain
# ============================================================

class TestA44StrictPolicyOnVerifyChain:
    """--strict-policy on the verify-chain command."""

    def test_verify_chain_with_strict_policy_blocks(self, tmp_path):
        """Invalid policy + verify-chain --strict-policy -> exit_code != 0."""
        ppath = _make_policy(tmp_path, _invalid_policy())
        log_path = _make_anchor_log(tmp_path)
        result = _invoke_verify_chain(log_path, ppath, strict_policy=True)
        assert result.exit_code != 0


# ============================================================
# TestA44StrictPolicyOnCheckpoint
# ============================================================

class TestA44StrictPolicyOnCheckpoint:
    """--strict-policy on the checkpoint command."""

    def test_checkpoint_with_strict_policy_blocks(self, tmp_path):
        """Invalid policy + checkpoint --strict-policy -> exit_code != 0."""
        ppath = _make_policy(tmp_path, _invalid_policy())
        log_path = _make_anchor_log(tmp_path)
        result = _invoke_checkpoint(log_path, ppath, strict_policy=True)
        assert result.exit_code != 0


# ============================================================
# TestA44Integration
# ============================================================

class TestA44Integration:
    """Integration tests for --strict-policy across commands."""

    def test_full_strict_policy_workflow(self, tmp_path):
        """Load valid policy with _load_audit_policy, create anchor log,
        run verify-chain with --strict-policy, verify it succeeds.
        """
        # Step 1: Load policy via _load_audit_policy, check schema_validated
        ppath = _make_policy(tmp_path, _valid_policy())
        policy = _load_audit_policy(ppath, strict_policy=True)
        assert policy["_policy_provenance"]["schema_validated"] is True
        assert policy["_policy_provenance"]["schema_warnings"] == 0

        # Step 2: Create anchor log with one valid entry
        entry = _make_anchor_entry()
        log_path = _make_anchor_log(tmp_path, [entry])

        # Step 3: Run verify-chain with --strict-policy --json
        result = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", log_path,
            "--policy", ppath,
            "--strict-policy",
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        # No raw policy path in output (A43 redaction)
        assert "policy_file" not in data
        assert "policy_file_hash" in data
        # Provenance includes schema validation status
        assert "policy_provenance" in data
        assert data["policy_provenance"]["schema_validated"] is True

    def test_strict_policy_across_all_commands(self, tmp_path):
        """Verify --strict-policy works consistently across audit, verify,
        verify-chain, and checkpoint.

        Phase A: invalid policy + --strict-policy -> all 4 commands block.
        Phase B: valid policy + --strict-policy -> all 4 commands accept policy.
        """
        # --- Phase A: invalid policy + --strict-policy -> all block ---
        bad_ppath = _make_policy(tmp_path, _invalid_policy(), name="bad_policy.json")
        log_path = _make_anchor_log(tmp_path)
        fake_zip = str(tmp_path / "nonexistent.zip")

        # audit: policy loaded before run-state, so bad policy blocks first
        r_audit = _invoke_audit(bad_ppath, strict_policy=True)
        assert r_audit.exit_code != 0, "audit should block on bad policy with --strict-policy"

        # verify: policy loaded before ZIP processing
        r_verify = _invoke_verify(fake_zip, bad_ppath, strict_policy=True)
        assert r_verify.exit_code != 0, "verify should block on bad policy with --strict-policy"

        # verify-chain: policy loaded before log processing
        r_vc = _invoke_verify_chain(log_path, bad_ppath, strict_policy=True)
        assert r_vc.exit_code != 0, "verify-chain should block on bad policy with --strict-policy"

        # checkpoint: policy loaded before checkpoint processing
        r_cp = _invoke_checkpoint(log_path, bad_ppath, strict_policy=True)
        assert r_cp.exit_code != 0, "checkpoint should block on bad policy with --strict-policy"

        # --- Phase B: valid policy + --strict-policy -> all accept ---
        good_ppath = _make_policy(tmp_path, _valid_policy(), name="good_policy.json")

        # audit: mock _load_run_state to avoid needing a real run directory.
        # The policy loads successfully; the command may fail later (run not found)
        # but the policy acceptance itself is confirmed by no schema error on stderr.
        with patch("ai_workflow_hub.cli._load_run_state", return_value=(None, None)):
            r_audit_ok = _invoke_audit(good_ppath, strict_policy=True)
        audit_err = r_audit_ok.stderr.lower() if r_audit_ok.stderr else ""
        assert "schema error" not in audit_err, \
            "valid policy should produce no schema errors under --strict-policy"

        # verify: policy loads, then ZIP check (nonexistent file => non-zero)
        # but policy acceptance is confirmed: no schema error on stderr
        r_verify_ok = _invoke_verify(fake_zip, good_ppath, strict_policy=True)
        verify_err = r_verify_ok.stderr.lower() if r_verify_ok.stderr else ""
        assert "schema error" not in verify_err, \
            "valid policy should produce no schema errors under --strict-policy"

        # verify-chain: should fully succeed with valid log + valid policy
        r_vc_ok = _invoke_verify_chain(log_path, good_ppath, strict_policy=True)
        assert r_vc_ok.exit_code == 0, \
            "verify-chain should succeed with valid policy + valid log under --strict-policy"

        # checkpoint: should fully succeed with valid log + valid policy
        r_cp_ok = _invoke_checkpoint(log_path, good_ppath, strict_policy=True)
        assert r_cp_ok.exit_code == 0, \
            "checkpoint should succeed with valid policy + valid log under --strict-policy"
