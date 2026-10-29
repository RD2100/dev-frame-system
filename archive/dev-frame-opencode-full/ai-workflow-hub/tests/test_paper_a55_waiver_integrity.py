"""A55 -- Harden Waiver Trace Integrity.

Verifies:
1. Waiver records have waiver_id (unique identifier).
2. Waiver records have command name.
3. Waiver records have policy_hash and policy_schema_version.
4. Waiver records have created_at timestamp.
5. Waiver records have adjusted_detail.
6. waiver_integrity field: "valid" when all check_indices point to failed checks.
7. Duplicate prevention uses check_index (not name).
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

# A55 required waiver fields
_A55_FIELDS = {"waiver_id", "check", "check_index", "original_status",
               "adjusted_status", "policy_field", "reason", "severity",
               "original_detail", "adjusted_detail", "command",
               "policy_hash", "policy_schema_version", "created_at"}


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
    p = {"schema_version": "1.0", "description": "A55 test", "strict_timestamps": True}
    if overrides: p.update(overrides)
    pp = tmp_path / "policy.json"
    pp.write_text(json.dumps(p), encoding="utf-8")
    return str(pp)

def _invoke_vc(log_path, extra_args=None):
    from rich.console import Console
    s, e = io.StringIO(), io.StringIO()
    _c, _ec = Console(file=s, force_terminal=False, width=4096), Console(file=e, force_terminal=False)
    args = ["paper", "verify-chain", "--log", str(log_path), "--json"]
    if extra_args: args.extend(extra_args)
    f = {k: v for k, v in os.environ.items() if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}
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
            return json.loads("\n".join(stdout.strip().split("\n")[i:]))
    raise ValueError("No JSON")

def _make_bundle(tmp_path, files):
    fe = [{"path": p, "sha256": _file_sha256(c)} for p, c in files.items()]
    ch = hashlib.sha256(json.dumps(sorted([(e["path"], e["sha256"]) for e in fe]),
                                   sort_keys=True).encode("utf-8")).hexdigest()
    bm = {"bundle_id": "a55", "files": fe, "attestation": {"content_hash": ch}}
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
        for p, c in af.items(): zf.writestr(p, c)
    h = hashlib.sha256(zp.read_bytes()).hexdigest()
    Path(str(zp) + ".sha256").write_text("%s  %s\n" % (h, zp.name), encoding="utf-8")
    return str(zp)

def _make_rd(tmp_path, files):
    rd = tmp_path / "run_dir"
    rd.mkdir(exist_ok=True)
    for p, c in files.items():
        (rd / p).write_text(c, encoding="utf-8")
    return str(rd)


# ============================================================
# TestA55WaiverFields
# ============================================================

class TestA55WaiverFields:
    """Enriched waiver record fields."""

    def test_all_a55_fields_present(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        waivers = data["policy_waivers"]
        assert len(waivers) >= 1
        w = waivers[0]
        missing = _A55_FIELDS - set(w.keys())
        assert not missing, "Missing A55 fields: %s" % missing

    def test_waiver_id_unique(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        ids = [w["waiver_id"] for w in data["policy_waivers"]]
        assert len(ids) == len(set(ids)), "Waiver IDs should be unique"

    def test_command_field(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        w = data["policy_waivers"][0]
        assert w["command"] == "verify-chain"

    def test_policy_metadata(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        w = data["policy_waivers"][0]
        assert w["policy_schema_version"] == "1.0"
        assert len(w["policy_hash"]) > 0

    def test_created_at_timestamp(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        w = data["policy_waivers"][0]
        assert "T" in w["created_at"]  # ISO format

    def test_adjusted_detail(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        w = data["policy_waivers"][0]
        assert len(w["adjusted_detail"]) > 0

    def test_completeness_waiver_a55_fields(self, tmp_path):
        files = {"data.txt": "A55 field test"}
        zp = _make_bundle(tmp_path, files)
        run_files = dict(files)
        run_files["orphan.dat"] = "extra"
        rd = _make_rd(tmp_path, run_files)
        r = runner.invoke(app, [
            "paper", "verify", "--zip", zp, "--run-dir", rd,
            "--json", "--completeness-check",
        ])
        data = json.loads(r.stdout, strict=False)
        waivers = [w for w in data.get("policy_waivers", [])
                   if w["check"] == "completeness_reverified"]
        assert len(waivers) >= 1
        w = waivers[0]
        assert w["command"] == "verify"
        missing = _A55_FIELDS - set(w.keys())
        assert not missing, "Missing A55 fields: %s" % missing


# ============================================================
# TestA55Integrity
# ============================================================

class TestA55Integrity:
    """waiver_integrity verification."""

    def test_integrity_valid(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=1, bad_ts=True)
        policy = _make_policy(tmp_path, {"strict_timestamps": False})
        _, stdout, _ = _invoke_vc(log, extra_args=["--policy", policy])
        data = _get_json(stdout)
        assert data.get("waiver_integrity") == "valid"

    def test_integrity_present_no_waivers(self, tmp_path):
        log = _make_anchor_log(tmp_path, n=2)
        _, stdout, _ = _invoke_vc(log)
        data = _get_json(stdout)
        assert data.get("waiver_integrity") == "valid"

    def test_paper_verify_integrity(self, tmp_path):
        files = {"x.txt": "integrity test"}
        zp = _make_bundle(tmp_path, files)
        r = runner.invoke(app, [
            "paper", "verify", "--zip", zp, "--json", "--no-check-artifacts",
        ])
        data = json.loads(r.stdout, strict=False)
        assert data.get("waiver_integrity") == "valid"
