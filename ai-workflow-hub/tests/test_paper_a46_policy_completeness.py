"""A46 -- Policy-Governed Completeness Proof.

Verifies:
1. Policy-controlled artifact classification (ignored_artifacts, generated_artifacts)
2. Hash-redacted missing file reporting (missing_from_bundle contains dicts, not strings)
3. completeness_strict policy field (blocking failures when true)
4. --completeness-check on verify-chain (re-verifies completeness claims)
5. --run-dir option on verify-chain (used with --completeness-check)
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

from ai_workflow_hub.cli import app, _load_audit_policy

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_policy(tmp_path, policy_dict, name="policy.json"):
    """Write a policy dict to a JSON file and return the path as string."""
    p = tmp_path / name
    p.write_text(json.dumps(policy_dict), encoding="utf-8")
    return str(p)


def _valid_policy(**overrides):
    """Return a valid audit policy dict with optional overrides."""
    base = {
        "schema_version": "1.0",
        "signature_policy": "optional",
        "chain_verification_mode": "chain_only",
        "allowed_key_ids": [],
        "required_artifacts": [],
        "strict_chain": False,
        "strict_timestamps": True,
        "description": "test-policy-a46",
    }
    base.update(overrides)
    return base


def _make_state(run_id="test-a46"):
    """Return a minimal valid paper run state dict."""
    return {
        "run_id": run_id,
        "task_id": "",
        "evidence_manifest": {"files": []},
        "ledger_dir": "",
        "decision_base_dir": "",
        "closeout_integrity": "complete",
    }


def _make_run_dir(tmp_path, run_id="test-a46", extra_files=None):
    """Create a mock paper run directory with required files.

    Returns (state_dict, run_dir_path).
    """
    rd = tmp_path / "runs" / run_id
    rd.mkdir(parents=True, exist_ok=True)

    state = _make_state(run_id)
    (rd / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (rd / "closeout-report.json").write_text(
        json.dumps({"run_id": run_id, "status": "complete"}),
        encoding="utf-8",
    )
    (rd / "closeout-report.md").write_text(
        f"# Closeout Report: {run_id}",
        encoding="utf-8",
    )

    if extra_files:
        for name, content in extra_files.items():
            fpath = rd / name
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

    return state, rd


def _make_anchor_entry(**overrides):
    """Create a minimal valid anchor log entry as a JSON string."""
    entry = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "bundle_id": "bundle-a46",
        "run_id": "run-a46",
        "zip_sha256": "a" * 64,
        "bundle_hash": "b" * 64,
        "signed": False,
        "prev_hash": "",
    }
    entry.update(overrides)
    return json.dumps(entry, separators=(",", ":"))


def _make_anchor_log(tmp_path, entries=None, name="anchor.jsonl"):
    """Write anchor log entries to a JSONL file and return the path as string."""
    if entries is None:
        entries = [_make_anchor_entry()]
    log = tmp_path / name
    log.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return str(log)


def _invoke_audit(run_id, output_zip, completeness=False,
                  as_json=False, policy_path=None):
    """Build and invoke 'paper audit' with given flags."""
    args = [
        "paper", "audit",
        "--run-id", run_id,
        "--output", str(output_zip),
    ]
    if completeness:
        args.append("--completeness-check")
    if as_json:
        args.append("--json")
    if policy_path:
        args.extend(["--policy", str(policy_path)])
    return runner.invoke(app, args)


# ============================================================
# TestA46PolicyFields
# ============================================================

class TestA46PolicyFields:
    """Policy fields: ignored_artifacts, generated_artifacts, completeness_strict."""

    def test_ignored_artifacts_in_policy(self, tmp_path):
        """Policy with ignored_artifacts field loads correctly with values preserved."""
        policy = _valid_policy(ignored_artifacts=["*.log", "cache/*"])
        ppath = _make_policy(tmp_path, policy)
        loaded = _load_audit_policy(ppath)
        assert "ignored_artifacts" in loaded
        assert loaded["ignored_artifacts"] == ["*.log", "cache/*"]

    def test_generated_artifacts_in_policy(self, tmp_path):
        """Policy with generated_artifacts field loads correctly with values preserved."""
        policy = _valid_policy(generated_artifacts=["scratch.tmp", "build-output/"])
        ppath = _make_policy(tmp_path, policy)
        loaded = _load_audit_policy(ppath)
        assert "generated_artifacts" in loaded
        assert loaded["generated_artifacts"] == ["scratch.tmp", "build-output/"]

    def test_completeness_strict_in_policy(self, tmp_path):
        """Policy with completeness_strict field loads correctly as True."""
        policy = _valid_policy(completeness_strict=True)
        ppath = _make_policy(tmp_path, policy)
        loaded = _load_audit_policy(ppath)
        assert "completeness_strict" in loaded
        assert loaded["completeness_strict"] is True


# ============================================================
# TestA46CompletenessClassification
# ============================================================

class TestA46CompletenessClassification:
    """Policy-controlled artifact classification in completeness check."""

    def test_ignored_patterns_excluded(self, tmp_path):
        """Files matching ignored_artifacts patterns are excluded from missing report."""
        run_id = "test-a46-ignored"
        state, rd = _make_run_dir(
            tmp_path, run_id,
            extra_files={
                "debug.log": "debug trace output",
                "app.log": "application log line",
            },
        )
        output_zip = str(tmp_path / "bundle-output.zip")
        policy = _valid_policy(ignored_artifacts=["*.log"])
        ppath = _make_policy(tmp_path, policy, name="policy_ignored.json")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True, as_json=True,
                policy_path=ppath,
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        comp = data["completeness"]
        # Ignored files excluded -- completeness should pass
        assert comp["complete"] is True
        assert comp["missing_count"] == 0
        # total_ignored reflects the excluded file count
        assert comp["total_ignored"] >= 2

    def test_generated_patterns_excluded(self, tmp_path):
        """Files matching generated_artifacts entries are excluded from missing report.

        Note: generated_artifacts values are added to the audit-generated set
        and matched via exact string comparison (not glob), so the policy must
        list exact filenames.
        """
        run_id = "test-a46-generated"
        state, rd = _make_run_dir(
            tmp_path, run_id,
            extra_files={
                "scratch.tmp": "temporary scratch data",
                "notes.tmp": "temporary notes",
            },
        )
        output_zip = str(tmp_path / "bundle-output.zip")
        # generated_artifacts uses exact-match against relative paths
        policy = _valid_policy(generated_artifacts=["scratch.tmp", "notes.tmp"])
        ppath = _make_policy(tmp_path, policy, name="policy_generated.json")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True, as_json=True,
                policy_path=ppath,
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        comp = data["completeness"]
        # Generated files excluded from the completeness check
        assert comp["complete"] is True
        assert comp["missing_count"] == 0

    def test_hash_redacted_missing(self, tmp_path):
        """Missing files are reported with path_hash and basename, not raw paths."""
        run_id = "test-a46-redact"
        state, rd = _make_run_dir(
            tmp_path, run_id,
            extra_files={
                "secret-data.txt": "sensitive content here",
            },
        )
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True, as_json=True,
            )

        data = json.loads(result.stdout, strict=False)
        comp = data["completeness"]
        assert comp["missing_count"] > 0
        assert len(comp["missing_from_bundle"]) > 0

        # Each missing entry must be a dict with path_hash and basename
        for entry in comp["missing_from_bundle"]:
            assert isinstance(entry, dict), (
                f"missing_from_bundle entry should be dict, got {type(entry).__name__}"
            )
            assert "path_hash" in entry
            assert "basename" in entry
            # path_hash is a truncated hex digest (16 chars)
            assert len(entry["path_hash"]) == 16
            # All hex characters
            int(entry["path_hash"], 16)
            # basename is just the filename, not the full path
            assert "/" not in entry["basename"]
            assert "\\" not in entry["basename"]


# ============================================================
# TestA46CompletenessStrict
# ============================================================

class TestA46CompletenessStrict:
    """completeness_strict policy field controls blocking behavior."""

    def test_strict_blocks_on_missing(self, tmp_path):
        """completeness_strict=true + missing files -> exit code 1."""
        run_id = "test-a46-strict-block"
        state, rd = _make_run_dir(
            tmp_path, run_id,
            extra_files={
                "orphan-file.dat": "orphan data not in bundle",
            },
        )
        output_zip = str(tmp_path / "bundle-output.zip")
        policy = _valid_policy(completeness_strict=True)
        ppath = _make_policy(tmp_path, policy, name="policy_strict.json")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True,
                policy_path=ppath,
            )

        assert result.exit_code == 1
        combined = (result.stdout or "") + (result.stderr or "")
        lower = combined.lower()
        assert "completeness strict" in lower or "strict" in lower

    def test_non_strict_warns_on_missing(self, tmp_path):
        """completeness_strict=false (default) + missing files -> exit code 0 (warning)."""
        run_id = "test-a46-nonstrict"
        state, rd = _make_run_dir(
            tmp_path, run_id,
            extra_files={
                "orphan-file.dat": "orphan data not in bundle",
            },
        )
        output_zip = str(tmp_path / "bundle-output.zip")
        # Default policy: completeness_strict is false
        policy = _valid_policy()
        ppath = _make_policy(tmp_path, policy, name="policy_nonstrict.json")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True,
                policy_path=ppath,
            )

        assert result.exit_code == 0
        combined = (result.stdout or "") + (result.stderr or "")
        assert "Completeness:" in combined


# ============================================================
# TestA46VerifyChainCompleteness
# ============================================================

class TestA46VerifyChainCompleteness:
    """--completeness-check and --run-dir on verify-chain command."""

    def test_verify_chain_has_completeness_option(self):
        """--completeness-check is a recognized option on verify-chain."""
        result = runner.invoke(app, ["paper", "verify-chain", "--help"])
        assert result.exit_code == 0
        combined = (result.stdout or "") + (result.stderr or "")
        assert "--completeness-check" in combined

    def test_verify_chain_completeness_claim_only(self, tmp_path):
        """verify-chain --completeness-check without --run-dir passes (claim-only)."""
        entry = _make_anchor_entry()
        log_path = _make_anchor_log(tmp_path, [entry])

        result = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", log_path,
            "--completeness-check",
            "--json",
        ])

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        # Completeness re-verification section present
        assert "completeness_reverification" in data
        comp = data["completeness_reverification"]
        assert len(comp) == 1
        # A49: Claim-only entries are NOT marked verified (correct behavior)
        assert comp[0]["verified"] is False
        assert comp[0].get("claim_only") is True
        assert "claim-only" in comp[0].get("note", "")

    def test_verify_chain_with_run_dir(self, tmp_path):
        """verify-chain --completeness-check --run-dir re-verifies ZIP in run directory."""
        # Create a fake ZIP file with known content
        zip_path = tmp_path / "audit-bundle-test.zip"
        zip_path.write_bytes(b"PK\x05\x06fake-zip-content")
        zip_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()

        # Create anchor log entry referencing this ZIP hash
        entry = _make_anchor_entry(zip_sha256=zip_sha256)
        log_path = _make_anchor_log(tmp_path, [entry])

        # Use tmp_path as run_dir (the ZIP is directly in tmp_path)
        result = runner.invoke(app, [
            "paper", "verify-chain",
            "--log", log_path,
            "--completeness-check",
            "--run-dir", str(tmp_path),
            "--json",
        ])

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        assert "completeness_reverification" in data
        comp = data["completeness_reverification"]
        assert len(comp) == 1
        # With run_dir: re-verification confirms the ZIP exists and matches
        assert comp[0]["verified"] is True
        assert comp[0].get("zip_verified") is True
