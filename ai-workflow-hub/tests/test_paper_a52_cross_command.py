"""A52 -- Cross-Command Consistency: Unified Raw-vs-Policy Model.

Verifies:
1. verify-chain: raw_verdict, policy_verdict, policy_waived_checks present.
2. verify-chain: exit code uses policy_verdict (not raw failed count).
3. verify-chain: timestamp downgrade (strict_timestamps=False) produces
   policy_waived entry instead of counter mutation.
4. paper verify: raw_trust_summary present alongside trust_summary.
5. verify-chain: raw_trust_summary present alongside trust_level.
6. Consistent field semantics across both commands.
"""

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app

runner = CliRunner()

_RT_PATH = "ai_workflow_hub.cli._paper_runtime"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_runtime():
    return {
        "sanitize": lambda rid: rid,
        "create": MagicMock(), "execute": MagicMock(),
        "status": MagicMock(), "redact": lambda s: s,
    }


def _make_anchor_log(tmp_path: Path, n: int = 2, name: str = "chain.log",
                     bad_timestamp: bool = False) -> str:
    """Create a minimal valid anchor log JSONL file.

    If bad_timestamp=True, the first entry will have a non-ISO timestamp
    (naive datetime without Z suffix, like A39 tests).  Use n=1 to avoid
    triggering timestamp_monotonic failures alongside.
    """
    log_path = tmp_path / name
    lines = []
    for i in range(n):
        if bad_timestamp and i == 0:
            ts = "2026-06-12T00:00:00"  # Naive: no Z suffix
        else:
            ts = "2026-06-13T00:0%d:00Z" % i
        entry = {
            "timestamp": ts,
            "bundle_id": "b%d" % i,
            "run_id": "r%d" % i,
            "zip_sha256": str(i) * 64,
            "bundle_hash": "h%d" % i,
            "signed": False,
        }
        if i > 0:
            prev_line = lines[-1]
            entry["prev_hash"] = hashlib.sha256(prev_line.encode("utf-8")).hexdigest()
        else:
            entry["prev_hash"] = ""
        lines.append(json.dumps(entry, ensure_ascii=False))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(log_path)


def _make_policy_file(tmp_path: Path, overrides: dict = None, name: str = "policy.json") -> str:
    """Create a minimal audit policy file. Returns path as string."""
    policy = {
        "schema_version": "1.0",
        "description": "A52 test policy",
        "strict_timestamps": True,
    }
    if overrides:
        policy.update(overrides)
    pp = tmp_path / name
    pp.write_text(json.dumps(policy), encoding="utf-8")
    return str(pp)


def _invoke_verify_chain(log_path, extra_args=None, env_overrides=None):
    """Invoke paper verify-chain with patched consoles."""
    from rich.console import Console

    rt = _fake_runtime()
    _runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "verify-chain", "--log", str(log_path), "--json"]
    if extra_args:
        args.extend(extra_args)

    filtered = {k: v for k, v in os.environ.items()
                if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}
    if env_overrides:
        filtered.update(env_overrides)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console), \
         patch.dict(os.environ, filtered, clear=True):
        result = _runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


def _get_json(stdout: str) -> dict:
    lines = stdout.strip().split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            return json.loads("\n".join(lines[i:]))
    raise ValueError("No JSON in stdout")


def _file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _make_bundle_zip(tmp_path: Path, files: dict, bundle_id: str = "a52") -> str:
    """Create a minimal valid audit bundle ZIP with sidecar. Returns path string."""
    file_entries = [{"path": p, "sha256": _file_sha256(c)} for p, c in files.items()]
    sorted_entries = sorted([(e["path"], e["sha256"]) for e in file_entries])
    content_hash = hashlib.sha256(
        json.dumps(sorted_entries, sort_keys=True).encode("utf-8")
    ).hexdigest()

    manifest = {
        "bundle_id": bundle_id,
        "files": file_entries,
        "attestation": {"content_hash": content_hash},
    }

    generated = {"bundle_manifest.json", "attestation.json",
                 "MANIFEST.json", "artifact_chain.json"}
    artifact_hashes = [
        {"artifact": e["path"], "sha256": e["sha256"]}
        for e in file_entries
        if e["path"] not in generated
    ]
    attestation = {"artifact_hashes": artifact_hashes}

    # All ZIP members
    all_files = dict(files)
    all_files["bundle_manifest.json"] = json.dumps(manifest, indent=2)
    all_files["attestation.json"] = json.dumps(attestation, indent=2)

    # MANIFEST.json with file index
    manifest_entries = []
    for path in sorted(all_files.keys()):
        manifest_entries.append({"path": path, "sha256": _file_sha256(all_files[path])})
    manifest_entries.append({"path": "MANIFEST.json", "sha256": ""})
    all_files["MANIFEST.json"] = json.dumps({"files": manifest_entries}, indent=2)

    # Write ZIP
    zp = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for path, content in all_files.items():
            zf.writestr(path, content)

    # Write sidecar
    actual_hash = hashlib.sha256(zp.read_bytes()).hexdigest()
    sidecar = Path(str(zp) + ".sha256")
    sidecar.write_text("%s  %s\n" % (actual_hash, zp.name), encoding="utf-8")

    return str(zp)


# ============================================================
# TestA52VerifyChainPolicyModel
# ============================================================

class TestA52VerifyChainPolicyModel:
    """verify-chain: raw_verdict, policy_verdict, policy_waived_checks."""

    def test_raw_verdict_present(self, tmp_path):
        """raw_verdict field always present in verify-chain output."""
        log = _make_anchor_log(tmp_path, n=2)
        result, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        assert "raw_verdict" in data
        assert data["raw_verdict"] in ("passed", "failed")

    def test_policy_verdict_present(self, tmp_path):
        """policy_verdict field always present in verify-chain output."""
        log = _make_anchor_log(tmp_path, n=2)
        result, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        assert "policy_verdict" in data
        assert data["policy_verdict"] in ("passed", "failed")

    def test_policy_waived_checks_present(self, tmp_path):
        """policy_waived_checks field always present (may be empty)."""
        log = _make_anchor_log(tmp_path, n=2)
        result, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        assert "policy_waived_checks" in data
        assert isinstance(data["policy_waived_checks"], list)

    def test_no_waivers_when_no_policy(self, tmp_path):
        """Without policy, policy_waived_checks is empty and raw==policy."""
        log = _make_anchor_log(tmp_path, n=2)
        result, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        assert data["policy_waived_checks"] == []
        assert data["raw_verdict"] == data["policy_verdict"]

    def test_timestamp_waiver_produces_policy_waived_entry(self, tmp_path):
        """strict_timestamps=False downgrades timestamp failure to waiver."""
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy_file(tmp_path, {"strict_timestamps": False})
        result, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        # Raw verdict should be "failed" (timestamp check failed originally)
        assert data["raw_verdict"] == "failed"
        # Policy verdict should be "passed" (waiver applied)
        assert data["policy_verdict"] == "passed"
        # Waived check should list timestamp_format_iso8601
        assert "timestamp_format_iso8601" in data["policy_waived_checks"]

    def test_exit_code_uses_policy_verdict(self, tmp_path):
        """Exit code is 0 when policy_verdict is 'passed' even if raw failed > 0."""
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy_file(tmp_path, {"strict_timestamps": False})
        result, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        assert data["policy_verdict"] == "passed"
        assert result.exit_code == 0, \
            f"Expected exit_code=0 for policy_verdict=passed, got {result.exit_code}"

    def test_exit_code_1_when_policy_verdict_failed(self, tmp_path):
        """Exit code is 1 when policy_verdict is 'failed'."""
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        # strict_timestamps=True (default) means timestamp failure is NOT waived
        policy = _make_policy_file(tmp_path, {"strict_timestamps": True})
        result, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        assert data["policy_verdict"] == "failed"
        assert result.exit_code == 1


# ============================================================
# TestA52RawTrustSummary
# ============================================================

class TestA52RawTrustSummary:
    """raw_trust_summary present in both paper verify and verify-chain."""

    def test_verify_chain_raw_trust_summary_present(self, tmp_path):
        """verify-chain output includes raw_trust_summary."""
        log = _make_anchor_log(tmp_path, n=2)
        result, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        assert "raw_trust_summary" in data
        assert isinstance(data["raw_trust_summary"], str)

    def test_verify_chain_raw_trust_matches_when_no_policy(self, tmp_path):
        """Without policy adjustments, raw_trust_summary matches trust_level base."""
        log = _make_anchor_log(tmp_path, n=2)
        result, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        # When no waivers, raw and policy trust should align
        _tl = data.get("trust_level", "unknown")
        assert data["raw_trust_summary"] == _tl

    def test_paper_verify_raw_trust_summary_present(self, tmp_path):
        """paper verify output includes raw_trust_summary."""
        files = {"data.txt": "test content A52"}
        zip_path = _make_bundle_zip(tmp_path, files)

        result = runner.invoke(app, [
            "paper", "verify", "--zip", zip_path, "--json",
            "--no-check-artifacts",
        ])
        data = json.loads(result.stdout, strict=False)
        assert "raw_trust_summary" in data
        assert isinstance(data["raw_trust_summary"], str)


# ============================================================
# TestA52ConsistentSemantics
# ============================================================

class TestA52ConsistentSemantics:
    """Both commands use consistent raw/policy verdict model."""

    def test_paper_verify_has_raw_and_policy_verdict(self, tmp_path):
        """paper verify output has both raw_verdict and policy_verdict."""
        files = {"report.txt": "report data A52"}
        zip_path = _make_bundle_zip(tmp_path, files)

        result = runner.invoke(app, [
            "paper", "verify", "--zip", zip_path, "--json",
            "--no-check-artifacts",
        ])
        data = json.loads(result.stdout, strict=False)
        assert "raw_verdict" in data
        assert "policy_verdict" in data
        assert data["raw_verdict"] in ("passed", "failed")
        assert data["policy_verdict"] in ("passed", "failed")

    def test_verdict_equals_policy_verdict_in_both_commands(self, tmp_path):
        """verdict field equals policy_verdict in both verify and verify-chain."""
        # paper verify
        files = {"x.txt": "content x"}
        zip_path = _make_bundle_zip(tmp_path, files)
        vr = runner.invoke(app, [
            "paper", "verify", "--zip", zip_path, "--json",
            "--no-check-artifacts",
        ])
        vd = json.loads(vr.stdout, strict=False)
        assert vd["verdict"] == vd["policy_verdict"]

        # verify-chain
        log = _make_anchor_log(tmp_path, n=2)
        _, stdout, _ = _invoke_verify_chain(log)
        cd = _get_json(stdout)
        assert cd["verdict"] == cd["policy_verdict"]

    def test_raw_failed_count_unchanged_by_waiver(self, tmp_path):
        """result['failed'] retains raw count even when waiver applies."""
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy_file(tmp_path, {"strict_timestamps": False})
        result, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        # failed count should still include the timestamp failure
        assert data["failed"] > 0, "raw failed count should include timestamp failure"
        # but policy_verdict should be passed
        assert data["policy_verdict"] == "passed"
        # raw_verdict should be failed
        assert data["raw_verdict"] == "failed"

    def test_verify_chain_waived_check_has_policy_waived_flag(self, tmp_path):
        """The individual check entry has policy_waived=True when waived."""
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy_file(tmp_path, {"strict_timestamps": False})
        result, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        ts_check = next(
            (c for c in data["checks"] if c["check"] == "timestamp_format_iso8601"),
            None
        )
        assert ts_check is not None, "timestamp check should exist"
        # A54: Raw check entry stays failed (immutable), waiver is in policy_waivers
        assert ts_check["passed"] is False, \
            "raw check entry should stay failed (immutable)"
        waivers = data.get("policy_waivers", [])
        ts_waivers = [w for w in waivers if w["check"] == "timestamp_format_iso8601"]
        assert len(ts_waivers) >= 1, \
            "timestamp waiver should exist in policy_waivers"
