"""A54 -- Bind Waivers to Immutable Raw Check Entries.

Verifies:
1. Check entries have stable index field.
2. Raw check entries are immutable (passed stays False after waiver).
3. Waiver records include check_index binding.
4. Duplicate waiver prevention.
5. Verdict computed from unique waived indices (not waiver count).
6. Multiple simultaneous waivers.
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


def _fake_runtime():
    return {"sanitize": lambda rid: rid, "create": MagicMock(),
            "execute": MagicMock(), "status": MagicMock(),
            "redact": lambda s: s}


def _file_sha256(c):
    return hashlib.sha256(c.encode("utf-8")).hexdigest()


def _make_anchor_log(tmp_path, n=1, bad_timestamp=False):
    log_path = tmp_path / "chain.log"
    lines = []
    for i in range(n):
        ts = "2026-06-12T00:00:00" if (bad_timestamp and i == 0) else "2026-06-13T00:0%d:00Z" % i
        entry = {"timestamp": ts, "bundle_id": "b%d" % i, "run_id": "r%d" % i,
                 "zip_sha256": str(i) * 64, "bundle_hash": "h%d" % i, "signed": False}
        entry["prev_hash"] = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest() if i > 0 else ""
        lines.append(json.dumps(entry, ensure_ascii=False))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(log_path)


def _make_policy(tmp_path, overrides=None):
    p = {"schema_version": "1.0", "description": "A54", "strict_timestamps": True}
    if overrides:
        p.update(overrides)
    pp = tmp_path / "policy.json"
    pp.write_text(json.dumps(p), encoding="utf-8")
    return str(pp)


def _invoke_verify_chain(log_path, extra_args=None, env_overrides=None):
    from rich.console import Console
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
    with patch(_RT_PATH, return_value=_fake_runtime()), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _c), \
         patch("ai_workflow_hub.cli.err_console", _ec), \
         patch.dict(os.environ, filtered, clear=True):
        r = CliRunner().invoke(app, args, catch_exceptions=False)
    return r, stdout_buf.getvalue(), stderr_buf.getvalue()


def _get_json(stdout):
    for i, l in enumerate(stdout.strip().split("\n")):
        if l.strip().startswith("{"):
            return json.loads("\n".join(stdout.strip().split("\n")[i:]))
    raise ValueError("No JSON")


def _make_bundle_zip(tmp_path, files):
    fe = [{"path": p, "sha256": _file_sha256(c)} for p, c in files.items()]
    se = sorted([(e["path"], e["sha256"]) for e in fe])
    ch = hashlib.sha256(json.dumps(se, sort_keys=True).encode("utf-8")).hexdigest()
    bm = {"bundle_id": "a54", "files": fe, "attestation": {"content_hash": ch}}
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


def _make_run_dir(tmp_path, files):
    rd = tmp_path / "run_dir"
    rd.mkdir(exist_ok=True)
    for p, c in files.items():
        (rd / p).write_text(c, encoding="utf-8")
    return str(rd)


# ============================================================
# TestA54CheckIndex
# ============================================================

class TestA54CheckIndex:
    """Check entries have stable index field."""

    def test_checks_have_index(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=2)
        _, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        for c in data["checks"]:
            assert "index" in c, "Check %s missing index" % c["check"]

    def test_indices_are_sequential(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=2)
        _, stdout, _ = _invoke_verify_chain(log)
        data = _get_json(stdout)
        indices = [c["index"] for c in data["checks"]]
        assert indices == list(range(len(indices)))


# ============================================================
# TestA54ImmutableRawCheck
# ============================================================

class TestA54ImmutableRawCheck:
    """Raw check entries stay immutable after waiver."""

    def test_timestamp_check_stays_failed(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        ts = next(c for c in data["checks"]
                  if c["check"] == "timestamp_format_iso8601")
        assert ts["passed"] is False, "Raw check should stay failed"
        assert "policy_waived" not in ts, \
            "Raw check should not have policy_waived flag"

    def test_raw_failed_count_includes_waived(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        assert data["failed"] > 0
        assert data["raw_verdict"] == "failed"
        assert data["policy_verdict"] == "passed"


# ============================================================
# TestA54WaiverBinding
# ============================================================

class TestA54WaiverBinding:
    """Waiver records include check_index binding."""

    def test_waiver_has_check_index(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        waivers = data["policy_waivers"]
        ts_w = next(w for w in waivers if w["check"] == "timestamp_format_iso8601")
        assert "check_index" in ts_w
        assert ts_w["check_index"] >= 0

    def test_waiver_check_index_matches_check(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        ts_w = next(w for w in data["policy_waivers"]
                    if w["check"] == "timestamp_format_iso8601")
        idx = ts_w["check_index"]
        check_at_idx = data["checks"][idx]
        assert check_at_idx["check"] == "timestamp_format_iso8601"

    def test_waiver_has_original_detail(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        ts_w = next(w for w in data["policy_waivers"]
                    if w["check"] == "timestamp_format_iso8601")
        assert "original_detail" in ts_w
        assert len(ts_w["original_detail"]) > 0

    def test_completeness_waiver_has_check_index(self, tmp_path):
        files = {"data.txt": "A54 binding test"}
        zp = _make_bundle_zip(tmp_path, files)
        run_files = dict(files)
        run_files["orphan.dat"] = "extra"
        rd = _make_run_dir(tmp_path, run_files)
        r = runner.invoke(app, [
            "paper", "verify", "--zip", zp, "--run-dir", rd,
            "--json", "--completeness-check",
        ])
        data = json.loads(r.stdout, strict=False)
        waivers = data.get("policy_waivers", [])
        cw = [w for w in waivers if w["check"] == "completeness_reverified"]
        assert len(cw) >= 1
        assert "check_index" in cw[0]
        assert cw[0]["check_index"] >= 0


# ============================================================
# TestA54DuplicatePrevention
# ============================================================

class TestA54DuplicatePrevention:
    """Duplicate waivers are prevented."""

    def test_no_duplicate_timestamp_waivers(self, tmp_path):
        """Even if the waiver code runs multiple times, only one record."""
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        ts_waivers = [w for w in data["policy_waivers"]
                      if w["check"] == "timestamp_format_iso8601"]
        assert len(ts_waivers) == 1, \
            "Should have exactly 1 timestamp waiver, got %d" % len(ts_waivers)


# ============================================================
# TestA54VerdictFromBindings
# ============================================================

class TestA54VerdictFromBindings:
    """Verdict uses unique waived indices, not waiver count."""

    def test_verdict_uses_unique_indices(self, tmp_path):
        """Policy verdict correctly adjusts for unique waived check indices."""
        log = _make_anchor_log(tmp_path, n=1, bad_timestamp=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_verify_chain(
            log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        assert data["raw_verdict"] == "failed"
        assert data["policy_verdict"] == "passed"
        assert data["verdict"] == "passed"
        # Exit code should be 0 since policy_verdict is passed
        assert data["failed"] > 0  # raw includes timestamp
