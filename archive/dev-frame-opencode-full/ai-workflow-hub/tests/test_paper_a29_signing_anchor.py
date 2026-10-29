"""A29 — Signing Anchor Tests.

Covers the 5 GPT-identified concerns from A28 accepted_with_limitations:

 1. Extend MANIFEST.json to index every ZIP member (v2.0)
 2. Verify persisted bundle_manifest with zip_sha256 (Check 10)
 3. Strengthen attestation_consistency to full set equality (Check 9)
 4. --no-check-artifacts → verification_mode: "metadata_only"
 5. Signing/external anchoring framework (Check 11 + --sign)
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers — reuse patterns from A28 tests
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a29") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a29",
        "project_id": "proj-a29", "status": "completed",
        "workflow_type": "paper",
        "created_at": "2026-06-12T00:00:00+00:00",
        "updated_at": "2026-06-12T00:01:00+00:00",
        "executed_nodes": ["plan", "execute"],
        "acceptance_result": {"status": "accepted", "reasons": [], "blocking_issues": []},
        "blocking_count": 0, "non_blocking_count": 0,
        "evidence_manifest": {
            "manifest_id": "ev-001", "status": "complete",
            "version": "1.0", "generated_at": "2026-06-12T00:00:30",
            "files": [],
            "privacy_attestation": {"no_full_text": True, "no_api_keys": True, "no_personal_identity": True},
        },
        "ledger_dir": "", "decision_base_dir": "",
    }
    _write_json(run_dir / "state.json", state)
    return run_dir, state


_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PAPER_RUNS = "ai_workflow_hub.cli._paper_runs_root"


def _fake_runtime():
    return {
        "sanitize": lambda rid: rid,
        "create": MagicMock(), "execute": MagicMock(),
        "status": MagicMock(), "redact": lambda s: s,
    }


def _invoke_audit(tmp_path, run_id="paper-a29-test", extra_args=None,
                  create_reports=True):
    """Run paper audit and return (result, run_dir, stdout, stderr)."""
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    run_dir, state = _make_run_dir(tmp_path, run_id)
    if create_reports:
        _write_json(run_dir / "closeout-report.json", {"v": 1, "run_id": run_id})
        (run_dir / "closeout-report.md").write_text(f"# Report {run_id}", encoding="utf-8")

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "audit", "--run-id", run_id]
    if extra_args:
        args.extend(extra_args)

    with patch(_RT_PATH, return_value=rt), \
         patch(_PAPER_RUNS, return_value=tmp_path), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, run_dir, stdout_buf.getvalue(), stderr_buf.getvalue()


def _invoke_verify(zip_path, extra_args=None, with_json=True):
    """Run paper verify and return (result, stdout, stderr)."""
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "verify", "--zip", str(zip_path)]
    if with_json:
        args.append("--json")
    if extra_args:
        args.extend(extra_args)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


def _find_audit_zip(run_dir: Path) -> Path:
    zips = list(run_dir.glob("audit-bundle-*.zip"))
    assert len(zips) == 1
    return zips[0]


def _get_json_from_stdout(stdout: str) -> dict:
    """Extract JSON from stdout (skip status lines)."""
    lines = stdout.strip().split("\n")
    json_start = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = i
            break
    if json_start < 0:
        raise ValueError("No JSON found in stdout")
    return json.loads("\n".join(lines[json_start:]))


# ===========================================================================
# 1. MANIFEST.json v2.0 — indexes every ZIP member
# ===========================================================================

class TestA29ManifestV2:
    def test_manifest_version_is_2(self, tmp_path):
        """MANIFEST.json should declare manifest_version='2.0'."""
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a29-mfv2")
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            mf = json.loads(zf.read("MANIFEST.json"))
            assert mf["manifest_version"] == "2.0"

    def test_manifest_includes_generated_members(self, tmp_path):
        """MANIFEST.json should index bundle_manifest.json, attestation.json, and itself."""
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a29-mfgen")
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            mf = json.loads(zf.read("MANIFEST.json"))
            paths = [e["path"] for e in mf["files"]]
            assert "bundle_manifest.json" in paths
            assert "attestation.json" in paths
            assert "MANIFEST.json" in paths

    def test_manifest_self_entry_has_empty_hash(self, tmp_path):
        """MANIFEST.json self-entry should have sha256='' (cannot hash itself)."""
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a29-mfself")
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            mf = json.loads(zf.read("MANIFEST.json"))
            self_entries = [e for e in mf["files"] if e["path"] == "MANIFEST.json"]
            assert len(self_entries) == 1
            assert self_entries[0]["sha256"] == ""
            assert self_entries[0]["size"] == 0

    def test_manifest_includes_evidence_files(self, tmp_path):
        """MANIFEST.json should also include all evidence files from the run."""
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a29-mfev")
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            mf = json.loads(zf.read("MANIFEST.json"))
            paths = [e["path"] for e in mf["files"]]
            assert "state.json" in paths
            assert "closeout-report.json" in paths
            assert "closeout-report.md" in paths

    def test_manifest_generated_member_hashes_valid(self, tmp_path):
        """Hashes for bundle_manifest.json and attestation.json should be correct."""
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a29-mfhash")
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            mf = json.loads(zf.read("MANIFEST.json"))
            for entry in mf["files"]:
                if entry["path"] == "MANIFEST.json":
                    continue  # skip self-entry
                content = zf.read(entry["path"])
                actual = hashlib.sha256(content).hexdigest()
                assert actual == entry["sha256"], \
                    f"Hash mismatch for {entry['path']}"


# ===========================================================================
# 2. Signing — --sign flag and HMAC-SHA256
# ===========================================================================

class TestA29Signing:
    def test_sign_with_key_produces_signature(self, tmp_path):
        """--sign with AIHUB_SIGNING_KEY should produce HMAC-SHA256 signature."""
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "test-secret-key"}):
            result, run_dir, _, _ = _invoke_audit(
                tmp_path, "a29-sign1", extra_args=["--sign"])
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            att = json.loads(zf.read("attestation.json"))
            assert "signature" in att
            sig = att["signature"]
            assert sig["algorithm"] == "HMAC-SHA256"
            assert len(sig["signature"]) == 64  # hex digest length
            assert "signed_at" in sig

    def test_sign_without_key_produces_none_algo(self, tmp_path):
        """--sign without AIHUB_SIGNING_KEY should produce algorithm='none'."""
        env = {k: v for k, v in os.environ.items() if k != "AIHUB_SIGNING_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result, run_dir, _, _ = _invoke_audit(
                tmp_path, "a29-sign2", extra_args=["--sign"])
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            att = json.loads(zf.read("attestation.json"))
            assert "signature" in att
            assert att["signature"]["algorithm"] == "none"
            assert att["signature"]["signature"] == ""

    def test_no_sign_flag_means_no_signature(self, tmp_path):
        """Without --sign, attestation should not have a signature field."""
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a29-nosign")
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            att = json.loads(zf.read("attestation.json"))
            assert "signature" not in att

    def test_signature_is_recomputable(self, tmp_path):
        """Given the same key, signature should be reproducible from attestation data."""
        key = "reproducible-key-123"
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result, run_dir, _, _ = _invoke_audit(
                tmp_path, "a29-sign-repro", extra_args=["--sign"])
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            att = json.loads(zf.read("attestation.json"))
            sig_block = att["signature"]
            # Rebuild: remove signature, recompute
            att_copy = {k: v for k, v in att.items() if k != "signature"}
            payload = json.dumps(att_copy, sort_keys=True, ensure_ascii=False).encode("utf-8")
            expected = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
            assert sig_block["signature"] == expected


# ===========================================================================
# 3. Verify Check 10 — Persisted Manifest zip_sha256
# ===========================================================================

class TestA29VerifyPersistedManifest:
    def test_verify_with_valid_run_dir(self, tmp_path):
        """Verify with --run-dir should pass persisted_manifest_zip_sha256."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-vpm-ok")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--run-dir", str(run_dir)])
        assert result_verify.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["persisted_manifest_zip_sha256"]["passed"] is True

    def test_verify_with_wrong_run_dir_fails(self, tmp_path):
        """Verify with --run-dir pointing to wrong manifest should fail."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-vpm-bad")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        # Corrupt the persisted manifest's zip_sha256
        bm_files = list(run_dir.glob("bundle_manifest_*.json"))
        assert len(bm_files) >= 1
        bm = json.loads(bm_files[0].read_text(encoding="utf-8"))
        bm["zip_sha256"] = "0" * 64
        bm_files[0].write_text(json.dumps(bm, indent=2), encoding="utf-8")

        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--run-dir", str(run_dir)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["persisted_manifest_zip_sha256"]["passed"] is False

    def test_verify_missing_persisted_manifest_fails(self, tmp_path):
        """--run-dir without persisted manifest should fail the check."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-vpm-miss")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        # Delete persisted manifests
        for f in run_dir.glob("bundle_manifest_*.json"):
            f.unlink()

        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--run-dir", str(run_dir)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["persisted_manifest_zip_sha256"]["passed"] is False

    def test_verify_without_run_dir_skips_check(self, tmp_path):
        """Without --run-dir, persisted_manifest_zip_sha256 should pass (skipped)."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-vpm-skip")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["persisted_manifest_zip_sha256"]["passed"] is True
        assert "skipped" in checks["persisted_manifest_zip_sha256"].get("detail", "")


# ===========================================================================
# 4. Verify Check 11 — Signature Verification
# ===========================================================================

class TestA29VerifySignature:
    def test_signed_bundle_verifies_with_correct_key(self, tmp_path):
        """Signed bundle should pass signature_valid with the same key."""
        key = "verify-key-abc"
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a29-vs-ok", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["signature_valid"]["passed"] is True

    def test_signed_bundle_fails_with_wrong_key(self, tmp_path):
        """Signed bundle should fail signature_valid with a different key."""
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "original-key"}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a29-vs-wrong", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "wrong-key"}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["signature_valid"]["passed"] is False

    def test_signed_bundle_fails_without_key(self, tmp_path):
        """Signed bundle should fail signature_valid when key is not set."""
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "orig-key"}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a29-vs-nokey", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        env = {k: v for k, v in os.environ.items() if k != "AIHUB_SIGNING_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["signature_valid"]["passed"] is False

    def test_unsigned_bundle_passes_signature_check(self, tmp_path):
        """Unsigned bundle should pass signature_valid ('no signature present')."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-vs-unsigned")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["signature_valid"]["passed"] is True


# ===========================================================================
# 5. Full set equality (Check 9 strengthened)
# ===========================================================================

class TestA29AttestationConsistency:
    def test_fresh_audit_has_full_set_equality(self, tmp_path):
        """A freshly generated audit should have perfect attestation consistency."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-att-eq")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["attestation_consistency"]["passed"] is True

    def test_detects_extra_in_bundle_manifest(self, tmp_path):
        """Tampered bundle_manifest with extra file should fail attestation_consistency."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-att-extra")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        # Tamper: add a fake file entry to bundle_manifest.json inside ZIP
        import shutil
        tampered_zip = tmp_path / "tampered.zip"
        shutil.copy(zip_path, tampered_zip)

        with zipfile.ZipFile(tampered_zip, "r") as zf_in:
            bm = json.loads(zf_in.read("bundle_manifest.json"))
            bm["files"].append({
                "path": "fake-evidence.json",
                "sha256": "0" * 64,
                "size": 100,
            })
            bm_bytes = json.dumps(bm, indent=2, ensure_ascii=False).encode("utf-8")
            all_names = zf_in.namelist()
            members = {}
            for name in all_names:
                members[name] = zf_in.read(name)

        with zipfile.ZipFile(tampered_zip, "w") as zf_out:
            for name, data in members.items():
                if name == "bundle_manifest.json":
                    zf_out.writestr(name, bm_bytes)
                else:
                    zf_out.writestr(name, data)

        result_verify, stdout, _ = _invoke_verify(tampered_zip)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["attestation_consistency"]["passed"] is False


# ===========================================================================
# 6. verification_mode field
# ===========================================================================

class TestA29VerificationMode:
    def test_full_mode_by_default(self, tmp_path):
        """Default verify should report verification_mode='full'."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-vm-full")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["verification_mode"] == "full"

    def test_metadata_only_mode(self, tmp_path):
        """--no-check-artifacts should report verification_mode='metadata_only'."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-vm-meta")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--no-check-artifacts"])
        data = _get_json_from_stdout(stdout)
        assert data["verification_mode"] == "metadata_only"


# ===========================================================================
# 7. End-to-end: full verify with all 11 checks
# ===========================================================================

class TestA29AllChecks:
    def test_all_12_checks_present_in_output(self, tmp_path):
        """Verify JSON should contain all 12 check entries."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-all11")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        check_names = [c["check"] for c in data["checks"]]
        expected = [
            "zip_exists", "zip_valid", "sidecar_hash_match",
            "bundle_manifest_present", "manifest_index_present",
            "attestation_present", "content_hash_valid",
            "manifest_file_hashes", "attestation_consistency",
            "persisted_manifest_zip_sha256", "signature_valid",
            "anchor_log_cross_verify",  # A32
        ]
        assert check_names == expected

    def test_fresh_audit_passes_all_12_checks(self, tmp_path):
        """A freshly generated audit should pass all 12 checks."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a29-pass11")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        assert result_verify.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["verdict"] == "passed"
        assert data["passed"] == 12
        assert data["failed"] == 0
