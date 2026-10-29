"""A53 -- Structured Policy-Waiver Trace Model.

Verifies:
1. policy_waivers list present in both paper verify and verify-chain.
2. Each waiver record has required fields: check, original_status,
   adjusted_status, policy_field, reason, severity.
3. Timestamp waiver in verify-chain produces structured record.
4. Completeness waiver in paper verify produces structured record.
5. Policy verdict computed from waiver records, not count subtraction.
6. No waiver records when no waivers apply (clean runs).
7. Backward-compat: policy_waived_checks still derived from waiver records.
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

# Required fields in each waiver record
_WAIVER_FIELDS = {"check", "original_status", "adjusted_status",
                  "policy_field", "reason", "severity"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_runtime():
    return {
        "sanitize": lambda rid: rid,
        "create": MagicMock(), "execute": MagicMock(),
        "status": MagicMock(), "redact": lambda s: s,
    }


def _file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _make_anchor_log(tmp_path, n=1, bad_timestamp=False):
    log_path = tmp_path / "chain.log"
    lines = []
    for i in range(n):
        if bad_timestamp and i == 0:
            ts = "2026-06-12T00:00:00"  # naive, no Z
        else:
            ts = "2026-06-13T00:0%d:00Z" % i
        entry = {
            "timestamp": ts,
            "bundle_id": "b%d" % i, "run_id": "r%d" % i,
            "zip_sha256": str(i) * 64, "bundle_hash": "h%d" % i,
            "signed": False,
        }
        if i > 0:
            entry["prev_hash"] = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()
        else:
            entry["prev_hash"] = ""
        lines.append(json.dumps(entry, ensure_ascii=False))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(log_path)


def _make_policy(tmp_path, overrides=None):
    policy = {"schema_version": "1.0", "description": "A53 test",
              "strict_timestamps": True}
    if overrides:
        policy.update(overrides)
    pp = tmp_path / "policy.json"
    pp.write_text(json.dumps(policy), encoding="utf-8")
    return str(pp)


def _invoke_verify_chain(log_path, extra_args=None, env_overrides=None):
    from rich.console import Console
    rt = _fake_runtime()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _c = Console(file=stdout_buf, force_terminal=False, width=4096)
    _ec = Console(file=stderr_buf, force_terminal=False)
    args = ["paper", "verify-chain", "--log", str(log_path), "--json"]
    if extra_args:
        args.extend(extra_args)
    filtered = {k: v for k, v in os.environ.items()
                if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}
    if env_overrides:
        filtered.update(env_overrides)
    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _c), \
         patch("ai_workflow_hub.cli.err_console", _ec), \
         patch.dict(os.environ, filtered, clear=True):
        r = CliRunner().invoke(app, args, catch_exceptions=False)
    return r, stdout_buf.getvalue(), stderr_buf.getvalue()


def _get_json(stdout):
    lines = stdout.strip().split("\n")
    for i, l in enumerate(lines):
        if l.strip().startswith("{"):
            return json.loads("\n".join(lines[i:]))
    raise ValueError("No JSON in stdout")


def _make_bundle_zip(tmp_path, files, bundle_id="a53"):
    file_entries = [{"path": p, "sha256": _file_sha256(c)} for p, c in files.items()]
    sorted_entries = sorted([(e["path"], e["sha256"]) for e in file_entries])
    content_hash = hashlib.sha256(
        json.dumps(sorted_entries, sort_keys=True).encode("utf-8")
    ).hexdigest()

    manifest = {
        "bundle_id": bundle_id, "files": file_entries,
        "attestation": {"content_hash": content_hash},
    }
    generated = {"bundle_manifest.json", "attestation.json",
                 "MANIFEST.json", "artifact_chain.json"}
    artifact_hashes = [
        {"artifact": e["path"], "sha256": e["sha256"]}
        for e in file_entries if e["path"] not in generated
    ]
    attestation = {"artifact_hashes": artifact_hashes}

    all_files = dict(files)
    all_files["bundle_manifest.json"] = json.dumps(manifest, indent=2)
    all_files["attestation.json"] = json.dumps(attestation, indent=2)

    manifest_entries = []
    for path in sorted(all_files.keys()):
        manifest_entries.append({"path": path, "sha256": _file_sha256(all_files[path])})
    manifest_entries.append({"path": "MANIFEST.json", "sha256": ""})
    all_files["MANIFEST.json"] = json.dumps({"files": manifest_entries}, indent=2)

    zp = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for path, content in all_files.items():
            zf.writestr(path, content)

    actual_hash = hashlib.sha256(zp.read_bytes()).hexdigest()
    sidecar = Path(str(zp) + ".sha256")
    sidecar.write_text("%s  %s\n" % (actual_hash, zp.name), encoding="utf-8")
    return str(zp)


def _make_run_dir(tmp_path, files):
    rd = tmp_path / "run_dir"
    rd.mkdir(exist_ok=True)
    for p, c in files.items():
        (rd / p).write_text(c, encoding="utf-8")
    return str(rd)


# ============================================================
# TestA53WaiverListPresent
# ============================================================

class TestA53WaiverListPresent:
    """policy_waivers list always present in both commands."""

    def test_verify_chain_has_policy_waivers(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=2)
        _, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        assert "policy_waivers" in data
        assert isinstance(data["policy_waivers"], list)

    def test_paper_verify_has_policy_waivers(self, tmp_path):
        files = {"doc.txt": "content A53"}
        zp = _make_bundle_zip(tmp_path, files)
        r = runner.invoke(app, [
            "paper", "verify", "--zip", zp, "--json", "--no-check-artifacts",
        ])
        data = json.loads(r.stdout, strict=False)
        assert "policy_waivers" in data
        assert isinstance(data["policy_waivers"], list)


# ============================================================
# TestA53TimestampWaiverRecord
# ============================================================

class TestA53TimestampWaiverRecord:
    """Timestamp waiver produces structured record."""

    def test_timestamp_waiver_record_fields(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        waivers = data["policy_waivers"]
        assert len(waivers) >= 1
        ts_waiver = next(w for w in waivers
                         if w["check"] == "timestamp_format_iso8601")
        # Check all required fields present
        for field in _WAIVER_FIELDS:
            assert field in ts_waiver, "Missing field: %s" % field
        # Check field values
        assert ts_waiver["original_status"] == "failed"
        assert ts_waiver["adjusted_status"] == "passed"
        assert ts_waiver["policy_field"] == "strict_timestamps"
        assert ts_waiver["severity"] == "warning"
        assert "strict_timestamps" in ts_waiver["reason"].lower()

    def test_no_waiver_when_strict_timestamps_true(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": True})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        # No waivers since strict_timestamps=True
        ts_waivers = [w for w in data["policy_waivers"]
                      if w["check"] == "timestamp_format_iso8601"]
        assert len(ts_waivers) == 0

    def test_no_waiver_when_all_checks_pass(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=2)  # Good timestamps
        _, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        assert data["policy_waivers"] == []


# ============================================================
# TestA53CompletenessWaiverRecord
# ============================================================

class TestA53CompletenessWaiverRecord:
    """Completeness non-strict waiver produces structured record."""

    def test_completeness_waiver_record(self, tmp_path):
        """Non-strict completeness failure creates waiver record."""
        files = {"data.txt": "test data A53"}
        zp = _make_bundle_zip(tmp_path, files)

        # Extra orphan file in run_dir causes completeness failure
        run_files = dict(files)
        run_files["orphan.dat"] = "extra file not in bundle"
        rd = _make_run_dir(tmp_path, run_files)

        r = runner.invoke(app, [
            "paper", "verify", "--zip", zp, "--run-dir", rd,
            "--json", "--completeness-check",
        ])
        data = json.loads(r.stdout, strict=False)

        waivers = data.get("policy_waivers", [])
        comp_waivers = [w for w in waivers
                        if w["check"] == "completeness_reverified"]
        assert len(comp_waivers) >= 1
        w = comp_waivers[0]
        for field in _WAIVER_FIELDS:
            assert field in w, "Missing field: %s" % field
        assert w["original_status"] == "failed"
        assert w["adjusted_status"] == "passed"
        assert w["policy_field"] == "completeness_strict"
        assert w["severity"] == "warning"

    def test_no_completeness_waiver_when_strict(self, tmp_path):
        """Strict completeness failure does NOT create waiver (it blocks)."""
        files = {"data.txt": "strict test A53"}
        zp = _make_bundle_zip(tmp_path, files)

        run_files = dict(files)
        run_files["orphan.dat"] = "extra file"
        rd = _make_run_dir(tmp_path, run_files)

        # Use a policy with completeness_strict=True
        policy = {"schema_version": "1.0", "description": "strict",
                  "completeness_strict": True}
        pp = tmp_path / "policy.json"
        pp.write_text(json.dumps(policy), encoding="utf-8")

        r = runner.invoke(app, [
            "paper", "verify", "--zip", zp, "--run-dir", rd,
            "--policy", str(pp), "--json", "--completeness-check",
        ])
        data = json.loads(r.stdout, strict=False)

        waivers = data.get("policy_waivers", [])
        comp_waivers = [w for w in waivers
                        if w["check"] == "completeness_reverified"]
        assert len(comp_waivers) == 0, \
            "Strict completeness should not produce waiver"


# ============================================================
# TestA53VerdictFromWaivers
# ============================================================

class TestA53VerdictFromWaivers:
    """Policy verdict computed from waiver records."""

    def test_policy_verdict_passed_with_waiver(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        assert len(data["policy_waivers"]) >= 1
        assert data["policy_verdict"] == "passed"
        assert data["raw_verdict"] == "failed"
        assert data["verdict"] == "passed"

    def test_policy_verdict_failed_without_waiver(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": True})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        ts_waivers = [w for w in data["policy_waivers"]
                      if w["check"] == "timestamp_format_iso8601"]
        assert len(ts_waivers) == 0
        assert data["policy_verdict"] == "failed"


# ============================================================
# TestA53BackwardCompat
# ============================================================

class TestA53BackwardCompat:
    """Backward compatibility: policy_waived_checks derived from waiver records."""

    def test_policy_waived_checks_from_waivers(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)

        waived_checks = data.get("policy_waived_checks", [])
        waiver_ids = [w["check"] for w in data["policy_waivers"]]
        assert set(waived_checks) == set(waiver_ids)

    def test_paper_verify_policy_waived_checks(self, tmp_path):
        files = {"report.txt": "A53 compat test"}
        zp = _make_bundle_zip(tmp_path, files)
        r = runner.invoke(app, [
            "paper", "verify", "--zip", zp, "--json", "--no-check-artifacts",
        ])
        data = json.loads(r.stdout, strict=False)
        assert "policy_waived_checks" in data
        assert isinstance(data["policy_waived_checks"], list)
