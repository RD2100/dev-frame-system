"""A56 -- Waiver Hash Binding and Adjusted-Check Map.

Verifies:
1. Waiver records have raw_check_hash field (16-char hex).
2. raw_check_hash matches recomputed SHA-256 of check entry snapshot.
3. Severity taxonomy: only valid values (info/warning/partial/block/accepted_risk).
4. Integrity verification detects raw_check_hash mismatch.
5. Invalid waivers (hash mismatch) are excluded from verdict adjustment.
6. adjusted_check_count field in result.
7. Multiple simultaneous waivers with valid hashes.
8. policy_waived_checks only includes integrity-validated waivers.
9. _valid_waiver_ids is removed from JSON output.
10. check_entry parameter produces correct hash.
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

from ai_workflow_hub.cli import app, _build_waiver_record, _verify_waiver_integrity

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.cli._paper_runtime"

_A56_SEVERITIES = {"info", "warning", "partial", "block", "accepted_risk"}


def _fake_runtime():
    return {"sanitize": lambda rid: rid, "create": MagicMock(),
            "execute": MagicMock(), "status": MagicMock(),
            "redact": lambda s: s}


def _file_sha256(c):
    return hashlib.sha256(c.encode("utf-8")).hexdigest()


def _make_anchor_log(tmp_path, n=1, bad_ts=False):
    lp = tmp_path / "chain.log"
    lines = []
    for i in range(n):
        ts = "2026-06-12T00:00:00" if (bad_ts and i == 0) else "2026-06-13T00:0%d:00Z" % i
        e = {"timestamp": ts, "bundle_id": "b%d" % i, "run_id": "r%d" % i,
             "zip_sha256": str(i) * 64, "bundle_hash": "h%d" % i, "signed": False}
        e["prev_hash"] = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest() if i > 0 else ""
        lines.append(json.dumps(e, ensure_ascii=False))
    lp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(lp)


def _make_policy(tmp_path, overrides=None):
    p = {"schema_version": "1.0", "description": "A56 test", "strict_timestamps": True}
    if overrides:
        p.update(overrides)
    pp = tmp_path / "policy.json"
    pp.write_text(json.dumps(p), encoding="utf-8")
    return str(pp)


def _invoke_vc(log_path, extra_args=None):
    from rich.console import Console
    s, e = io.StringIO(), io.StringIO()
    _c = Console(file=s, force_terminal=False, width=4096)
    _ec = Console(file=e, force_terminal=False)
    args = ["paper", "verify-chain", "--log", str(log_path), "--json"]
    if extra_args:
        args.extend(extra_args)
    f = {k: v for k, v in os.environ.items()
         if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}
    with patch(_RT_PATH, return_value=_fake_runtime()), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _c), \
         patch("ai_workflow_hub.cli.err_console", _ec), \
         patch.dict(os.environ, f, clear=True):
        r = CliRunner().invoke(app, args, catch_exceptions=False)
    return r, s.getvalue(), e.getvalue()


def _get_json(stdout):
    for i, l in enumerate(stdout.strip().split("\n")):
        if l.strip().startswith("{"):
            return json.loads("\n".join(stdout.strip().split("\n")[i:]), strict=False)
    raise ValueError("No JSON")


def _make_bundle(tmp_path, files):
    fe = [{"path": p, "sha256": _file_sha256(c)} for p, c in files.items()]
    ch = hashlib.sha256(json.dumps(sorted([(e["path"], e["sha256"]) for e in fe]),
                                   sort_keys=True).encode("utf-8")).hexdigest()
    bm = {"bundle_id": "a56", "files": fe, "attestation": {"content_hash": ch}}
    gen = {"bundle_manifest.json", "attestation.json", "MANIFEST.json", "artifact_chain.json"}
    ah = [{"artifact": e["path"], "sha256": e["sha256"]} for e in fe if e["path"] not in gen]
    att = {"artifact_hashes": ah}
    af = dict(files)
    af["bundle_manifest.json"] = json.dumps(bm, indent=2)
    af["attestation.json"] = json.dumps(att, indent=2)
    me = [{"path": p, "sha256": _file_sha256(af[p])} for p in sorted(af.keys())]
    me.append({"path": "MANIFEST.json", "sha256": ""})
    af["MANIFEST.json"] = json.dumps({"files": me}, indent=2)
    zp = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for p, c in af.items():
            zf.writestr(p, c)
    h = hashlib.sha256(zp.read_bytes()).hexdigest()
    Path(str(zp) + ".sha256").write_text("%s  %s\n" % (h, zp.name), encoding="utf-8")
    return str(zp)


def _make_rd(tmp_path, files):
    rd = tmp_path / "run_dir"
    rd.mkdir(exist_ok=True)
    for p, c in files.items():
        (rd / p).write_text(c, encoding="utf-8")
    return str(rd)


def _compute_check_hash(check_entry):
    """Recompute raw_check_hash from a check entry (same logic as _build_waiver_record)."""
    snapshot = json.dumps(
        {k: v for k, v in check_entry.items() if k != "index"},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(snapshot.encode("utf-8")).hexdigest()[:16]


# ============================================================
# TestA56RawCheckHash
# ============================================================

class TestA56RawCheckHash:
    """raw_check_hash field in waiver records."""

    def test_raw_check_hash_present(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        waivers = data["policy_waivers"]
        assert len(waivers) >= 1
        assert "raw_check_hash" in waivers[0]

    def test_raw_check_hash_16_hex(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        h = data["policy_waivers"][0]["raw_check_hash"]
        assert len(h) == 16
        int(h, 16)  # must be valid hex

    def test_raw_check_hash_matches_check_entry(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        # Find the timestamp check entry
        ts_check = next((c for c in data["checks"]
                         if c["check"] == "timestamp_format_iso8601"), None)
        assert ts_check is not None
        # Recompute hash from check entry
        expected = _compute_check_hash(ts_check)
        # Compare with waiver's raw_check_hash
        w = next(w for w in data["policy_waivers"]
                 if w["check"] == "timestamp_format_iso8601")
        assert w["raw_check_hash"] == expected


# ============================================================
# TestA56SeverityTaxonomy
# ============================================================

class TestA56SeverityTaxonomy:
    """Severity taxonomy validation."""

    def test_severity_field_present(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        assert "severity" in data["policy_waivers"][0]

    def test_severity_valid_value(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        sev = data["policy_waivers"][0]["severity"]
        assert sev in _A56_SEVERITIES

    def test_invalid_severity_defaults_to_warning(self):
        rec = _build_waiver_record(
            check_name="test", check_index=0, original_detail="fail",
            policy_field="test_field", reason="test", severity="INVALID",
            command="test-cmd")
        assert rec["severity"] == "warning"

    def test_all_valid_severities(self):
        for sev in _A56_SEVERITIES:
            rec = _build_waiver_record(
                check_name="test", check_index=0, original_detail="fail",
                policy_field="test_field", reason="test", severity=sev,
                command="test-cmd")
            assert rec["severity"] == sev


# ============================================================
# TestA56IntegrityHashBinding
# ============================================================

class TestA56IntegrityHashBinding:
    """Integrity verification with raw_check_hash validation."""

    def test_integrity_valid_with_hash(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        assert data["waiver_integrity"] == "valid"
        assert "waiver_integrity_issues" not in data

    def test_hash_mismatch_detected(self):
        """Manually corrupt raw_check_hash and verify integrity catches it."""
        result = {
            "checks": [
                {"check": "test_check", "passed": False, "detail": "failed"},
            ],
            "policy_waivers": [
                _build_waiver_record(
                    check_name="test_check", check_index=0,
                    original_detail="failed", policy_field="test",
                    reason="test", severity="warning", command="test",
                    check_entry={"check": "test_check", "passed": False, "detail": "failed"},
                ),
            ],
        }
        # Corrupt the hash
        result["policy_waivers"][0]["raw_check_hash"] = "deadbeef" * 2
        _verify_waiver_integrity(result)
        assert result["waiver_integrity"] == "invalid"
        issues = result["waiver_integrity_issues"]
        assert any(i["issue"] == "raw_check_hash_mismatch" for i in issues)

    def test_valid_hash_passes_integrity(self):
        """Waiver with correct hash passes integrity check."""
        entry = {"check": "test_check", "passed": False, "detail": "ok"}
        result = {
            "checks": [entry],
            "policy_waivers": [
                _build_waiver_record(
                    check_name="test_check", check_index=0,
                    original_detail="ok", policy_field="test",
                    reason="test", severity="warning", command="test",
                    check_entry=entry,
                ),
            ],
        }
        _verify_waiver_integrity(result)
        assert result["waiver_integrity"] == "valid"


# ============================================================
# TestA56AdjustedCheckMap
# ============================================================

class TestA56AdjustedCheckMap:
    """Adjusted-check map for verdict computation."""

    def test_adjusted_check_count_present(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        assert "adjusted_check_count" in data

    def test_adjusted_check_count_matches_waivers(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        n_waivers = len(data["policy_waivers"])
        assert data["adjusted_check_count"] == n_waivers

    def test_invalid_waivers_excluded_from_verdict(self):
        """Waivers with bad integrity should NOT adjust the verdict."""
        entry = {"check": "test_check", "passed": False, "detail": "fail"}
        result = {
            "checks": [entry],
            "failed": 1,
            "passed": 0,
            "policy_waivers": [
                {
                    "waiver_id": "bad_waiver",
                    "check": "test_check",
                    "check_index": 0,
                    "raw_check_hash": "WRONG_HASH_00000",  # Invalid
                    "severity": "warning",
                    "command": "test",
                },
            ],
        }
        _verify_waiver_integrity(result)
        assert result["waiver_integrity"] == "invalid"
        # Only valid waivers should be in _valid_waiver_ids
        valid_ids = result["_valid_waiver_ids"]
        assert "bad_waiver" not in valid_ids


# ============================================================
# TestA56MultipleWaivers
# ============================================================

class TestA56MultipleWaivers:
    """Multiple simultaneous waivers in a single result."""

    def test_multiple_waivers_all_valid(self):
        """Multiple waivers with correct hashes all pass integrity."""
        entries = [
            {"check": "check_a", "passed": False, "detail": "fail_a"},
            {"check": "check_b", "passed": False, "detail": "fail_b"},
        ]
        waivers = []
        for i, entry in enumerate(entries):
            waivers.append(_build_waiver_record(
                check_name=entry["check"], check_index=i,
                original_detail=entry["detail"], policy_field="field_%d" % i,
                reason="test", severity="warning", command="test",
                check_entry=entry,
            ))
        result = {
            "checks": entries,
            "failed": 2,
            "passed": 0,
            "policy_waivers": waivers,
        }
        _verify_waiver_integrity(result)
        assert result["waiver_integrity"] == "valid"
        assert len(result["_valid_waiver_ids"]) == 2

    def test_multiple_waivers_one_invalid(self):
        """One corrupted waiver out of multiple should only exclude that one."""
        entries = [
            {"check": "check_a", "passed": False, "detail": "fail_a"},
            {"check": "check_b", "passed": False, "detail": "fail_b"},
        ]
        w_good = _build_waiver_record(
            check_name="check_a", check_index=0,
            original_detail="fail_a", policy_field="f",
            reason="test", severity="warning", command="test",
            check_entry=entries[0])
        w_bad = _build_waiver_record(
            check_name="check_b", check_index=1,
            original_detail="fail_b", policy_field="f",
            reason="test", severity="warning", command="test",
            check_entry=entries[1])
        w_bad["raw_check_hash"] = "corrupted_hash0"  # Break integrity
        result = {
            "checks": entries,
            "failed": 2,
            "passed": 0,
            "policy_waivers": [w_good, w_bad],
        }
        _verify_waiver_integrity(result)
        assert result["waiver_integrity"] == "invalid"
        valid_ids = result["_valid_waiver_ids"]
        assert w_good["waiver_id"] in valid_ids
        assert w_bad["waiver_id"] not in valid_ids

    def test_policy_waived_checks_only_valid(self):
        """policy_waived_checks should only list integrity-validated waivers."""
        entry = {"check": "only_check", "passed": False, "detail": "fail"}
        good_waiver = _build_waiver_record(
            check_name="only_check", check_index=0,
            original_detail="fail", policy_field="f",
            reason="good", severity="warning", command="test",
            check_entry=entry)
        bad_waiver = _build_waiver_record(
            check_name="bad_check", check_index=0,
            original_detail="fail", policy_field="f",
            reason="bad", severity="warning", command="test",
            check_entry=entry)
        bad_waiver["raw_check_hash"] = "tampered_hash00"
        result = {
            "checks": [entry],
            "failed": 1,
            "passed": 0,
            "policy_waivers": [good_waiver, bad_waiver],
        }
        _verify_waiver_integrity(result)
        valid_ids = result["_valid_waiver_ids"]
        waived = [w["check"] for w in result["policy_waivers"]
                  if w.get("waiver_id", "") in valid_ids]
        assert "only_check" in waived
        assert "bad_check" not in waived


# ============================================================
# TestA56InternalKeysCleaned
# ============================================================

class TestA56InternalKeysCleaned:
    """Internal _valid_waiver_ids removed from JSON output."""

    def test_no_internal_keys_in_output(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        assert "_valid_waiver_ids" not in data

    def test_check_entry_produces_hash(self):
        """check_entry parameter in _build_waiver_record produces raw_check_hash."""
        entry = {"check": "my_check", "passed": False, "detail": "some detail"}
        rec = _build_waiver_record(
            check_name="my_check", check_index=0,
            original_detail="some detail", policy_field="f",
            reason="r", severity="info", command="test",
            check_entry=entry)
        expected = _compute_check_hash(entry)
        assert rec["raw_check_hash"] == expected

    def test_no_check_entry_uses_synthetic_snapshot(self):
        """Without check_entry, synthetic snapshot is used for hash."""
        rec = _build_waiver_record(
            check_name="synthetic", check_index=5,
            original_detail="detail_text", policy_field="f",
            reason="r", severity="partial", command="test")
        assert len(rec["raw_check_hash"]) == 16
        # Verify it's deterministic
        rec2 = _build_waiver_record(
            check_name="synthetic", check_index=5,
            original_detail="detail_text", policy_field="f",
            reason="r", severity="partial", command="test")
        # Note: created_at will differ, but raw_check_hash should match
        assert rec["raw_check_hash"] == rec2["raw_check_hash"]
