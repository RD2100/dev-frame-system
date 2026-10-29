"""A25 — Audit Package E2E tests.

Covers:
  1. _hash_file determinism
  2. _build_bundle_manifest attestation (content_hash + bundle_hash)
  3. _rehash_artifact_chain_with_reports extends chain
  4. _build_attestation_record structure
  5. _check_omitted_evidence detects unlisted files
  6. paper audit CLI end-to-end (ZIP creation + contents)
  7. Bundle manifest persisted alongside ZIP
  8. Omitted-evidence file written when unlisted files exist
  9. Artifact chain binds report files (tamper-evidence)
 10. Sanitize run_id protection in paper audit
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a25") -> tuple[Path, dict]:
    """Create a minimal paper run directory with state.json."""
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "run_id": run_id,
        "task_id": "task-a25",
        "project_id": "proj-a25",
        "status": "completed",
        "workflow_type": "paper",
        "created_at": "2026-06-12T00:00:00+00:00",
        "updated_at": "2026-06-12T00:01:00+00:00",
        "executed_nodes": ["plan", "execute", "review"],
        "acceptance_result": {
            "status": "accepted",
            "reasons": ["all checks pass"],
            "blocking_issues": [],
        },
        "blocking_count": 0,
        "non_blocking_count": 0,
        "evidence_manifest": {
            "manifest_id": "ev-manifest-001",
            "status": "complete",
            "version": "1.0",
            "generated_at": "2026-06-12T00:00:30+00:00",
            "files": [],
            "privacy_attestation": {
                "no_full_text": True,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
        },
        "ledger_dir": "",
        "decision_base_dir": "",
    }
    _write_json(run_dir / "state.json", state)
    return run_dir, state


# ---------------------------------------------------------------------------
# 1. _hash_file
# ---------------------------------------------------------------------------

class TestA25HashFile:
    def test_hash_file_deterministic(self, tmp_path):
        from ai_workflow_hub.cli import _hash_file
        f = tmp_path / "sample.txt"
        f.write_text("hello world", encoding="utf-8")
        h1 = _hash_file(f)
        h2 = _hash_file(f)
        assert h1 == h2
        assert h1 == hashlib.sha256(b"hello world").hexdigest()

    def test_hash_file_changes_on_modification(self, tmp_path):
        from ai_workflow_hub.cli import _hash_file
        f = tmp_path / "data.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        h1 = _hash_file(f)
        f.write_text('{"a": 2}', encoding="utf-8")
        h2 = _hash_file(f)
        assert h1 != h2


# ---------------------------------------------------------------------------
# 2. _build_bundle_manifest
# ---------------------------------------------------------------------------

class TestA25BundleManifest:
    def test_manifest_structure(self):
        from ai_workflow_hub.cli import _build_bundle_manifest
        files = [
            {"path": "a.json", "sha256": "aaa", "size": 10},
            {"path": "b.json", "sha256": "bbb", "size": 20},
        ]
        m = _build_bundle_manifest("bundle-001", "run-001", files, "2026-06-12T00:00:00")
        assert m["bundle_id"] == "bundle-001"
        assert m["run_id"] == "run-001"
        assert len(m["files"]) == 2
        assert "attestation" in m
        att = m["attestation"]
        assert "content_hash" in att
        assert "bundle_hash" in att
        assert att["timestamp"] == "2026-06-12T00:00:00"

    def test_content_hash_deterministic(self):
        from ai_workflow_hub.cli import _build_bundle_manifest
        files = [
            {"path": "a.json", "sha256": "aaa", "size": 10},
            {"path": "b.json", "sha256": "bbb", "size": 20},
        ]
        m1 = _build_bundle_manifest("b1", "r1", files, "t1")
        m2 = _build_bundle_manifest("b1", "r1", files, "t1")
        assert m1["attestation"]["content_hash"] == m2["attestation"]["content_hash"]
        assert m1["attestation"]["bundle_hash"] == m2["attestation"]["bundle_hash"]

    def test_content_hash_changes_with_file_hash(self):
        from ai_workflow_hub.cli import _build_bundle_manifest
        files_a = [{"path": "a.json", "sha256": "aaa", "size": 10}]
        files_b = [{"path": "a.json", "sha256": "zzz", "size": 10}]
        ma = _build_bundle_manifest("b1", "r1", files_a, "t1")
        mb = _build_bundle_manifest("b1", "r1", files_b, "t1")
        assert ma["attestation"]["content_hash"] != mb["attestation"]["content_hash"]

    def test_bundle_hash_changes_with_id(self):
        from ai_workflow_hub.cli import _build_bundle_manifest
        files = [{"path": "a.json", "sha256": "aaa", "size": 10}]
        m1 = _build_bundle_manifest("b1", "r1", files, "t1")
        m2 = _build_bundle_manifest("b2", "r1", files, "t1")
        assert m1["attestation"]["bundle_hash"] != m2["attestation"]["bundle_hash"]


# ---------------------------------------------------------------------------
# 3. _rehash_artifact_chain_with_reports
# ---------------------------------------------------------------------------

class TestA25RehashArtifactChain:
    def test_extends_with_report_files(self, tmp_path):
        from ai_workflow_hub.cli import _rehash_artifact_chain_with_reports
        original = [{"artifact": "state.json", "sha256": "abc"}]
        rj = tmp_path / "closeout-report.json"
        rm = tmp_path / "closeout-report.md"
        rj.write_text('{"report": true}', encoding="utf-8")
        rm.write_text("# Report", encoding="utf-8")
        extended = _rehash_artifact_chain_with_reports(tmp_path, original, rj, rm)
        assert len(extended) == 3
        names = [e["artifact"] for e in extended]
        assert "closeout-report.json" in names
        assert "closeout-report.md" in names

    def test_skips_missing_report_files(self, tmp_path):
        from ai_workflow_hub.cli import _rehash_artifact_chain_with_reports
        original = [{"artifact": "state.json", "sha256": "abc"}]
        rj = tmp_path / "nonexistent.json"
        rm = tmp_path / "nonexistent.md"
        extended = _rehash_artifact_chain_with_reports(tmp_path, original, rj, rm)
        assert len(extended) == 1

    def test_report_hash_changes_on_content_modification(self, tmp_path):
        from ai_workflow_hub.cli import _rehash_artifact_chain_with_reports, _hash_file
        rj = tmp_path / "closeout-report.json"
        rm = tmp_path / "closeout-report.md"
        rj.write_text('{"v": 1}', encoding="utf-8")
        rm.write_text("# V1", encoding="utf-8")
        ext1 = _rehash_artifact_chain_with_reports(tmp_path, [], rj, rm)
        rj.write_text('{"v": 2}', encoding="utf-8")
        ext2 = _rehash_artifact_chain_with_reports(tmp_path, [], rj, rm)
        h1 = [e for e in ext1 if e["artifact"] == "closeout-report.json"][0]["sha256"]
        h2 = [e for e in ext2 if e["artifact"] == "closeout-report.json"][0]["sha256"]
        assert h1 != h2


# ---------------------------------------------------------------------------
# 4. _build_attestation_record
# ---------------------------------------------------------------------------

class TestA25AttestationRecord:
    def test_attestation_structure(self):
        from ai_workflow_hub.cli import _build_attestation_record
        chain = [{"artifact": "state.json", "sha256": "abc"}]
        att = _build_attestation_record("run-1", "bundle-1", "2026-06-12", "ch-xyz", chain, "complete")
        assert att["run_id"] == "run-1"
        assert att["bundle_id"] == "bundle-1"
        assert att["timestamp"] == "2026-06-12"
        assert att["content_hash"] == "ch-xyz"
        assert att["closeout_integrity"] == "complete"
        assert att["report_version"] == "1.0"
        assert att["workflow_type"] == "paper"
        assert len(att["artifact_hashes"]) == 1
        assert att["artifact_hashes"][0]["artifact"] == "state.json"

    def test_attestation_reflects_integrity(self):
        from ai_workflow_hub.cli import _build_attestation_record
        att_complete = _build_attestation_record("r", "b", "t", "h", [], "complete")
        att_partial = _build_attestation_record("r", "b", "t", "h", [], "partial")
        assert att_complete["closeout_integrity"] == "complete"
        assert att_partial["closeout_integrity"] == "partial"


# ---------------------------------------------------------------------------
# 5. _check_omitted_evidence
# ---------------------------------------------------------------------------

class TestA25OmittedEvidence:
    def test_detects_unlisted_files(self, tmp_path):
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Listed file
        (run_dir / "listed.json").write_text("{}", encoding="utf-8")
        # Unlisted file
        (run_dir / "extra-notes.json").write_text("{}", encoding="utf-8")
        manifest = {"files": [{"path": "listed.json", "sha256": "x"}]}
        omitted = _check_omitted_evidence(run_dir, manifest)
        assert "extra-notes.json" in omitted
        assert "listed.json" not in omitted

    def test_excludes_known_prefixes(self, tmp_path):
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        for name in ["bundle_manifest_x.json", "attestation_y.json",
                      "closeout-report.json", "artifact_chain.json",
                      "omitted-evidence.json"]:
            (run_dir / name).write_text("{}", encoding="utf-8")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        assert omitted == []

    def test_empty_manifest_detects_all(self, tmp_path):
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "mystery.json").write_text("{}", encoding="utf-8")
        (run_dir / "readme.txt").write_text("hi", encoding="utf-8")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        assert "mystery.json" in omitted
        assert "readme.txt" in omitted

    def test_ignores_non_matching_extensions(self, tmp_path):
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "image.png").write_bytes(b"\x89PNG")
        (run_dir / "binary.exe").write_bytes(b"\x00")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        assert omitted == []


# ---------------------------------------------------------------------------
# 6. paper audit CLI — E2E with mocked runtime
# ---------------------------------------------------------------------------

_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PAPER_RUNS = "ai_workflow_hub.cli._paper_runs_root"


def _fake_runtime(run_dir: Path, run_id: str):
    """Return a mock _paper_runtime dict."""
    return {
        "sanitize": lambda rid: rid,
        "create": MagicMock(),
        "execute": MagicMock(),
        "status": MagicMock(),
        "redact": lambda s: s,
    }


class TestA25PaperAuditCLI:
    """Integration tests for `paper audit` CLI command."""

    def _invoke_audit(self, tmp_path, run_id="paper-audit-test"):
        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app

        run_dir, state = _make_run_dir(tmp_path, run_id)

        # Create closeout reports so audit doesn't try to generate them
        _write_json(run_dir / "closeout-report.json", {"report_version": "1.0", "run_id": run_id})
        (run_dir / "closeout-report.md").write_text(f"# Report {run_id}", encoding="utf-8")

        rt = _fake_runtime(run_dir, run_id)
        runner = CliRunner()

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"):
            result = runner.invoke(app, ["paper", "audit", "--run-id", run_id],
                                   catch_exceptions=False)
        return result, run_dir

    def test_audit_creates_zip(self, tmp_path):
        result, run_dir = self._invoke_audit(tmp_path)
        assert result.exit_code == 0
        # Find the ZIP
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        assert len(zips) == 1

    def test_audit_zip_contains_required_files(self, tmp_path):
        result, run_dir = self._invoke_audit(tmp_path)
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        assert len(zips) == 1
        with zipfile.ZipFile(zips[0], "r") as zf:
            names = zf.namelist()
            assert "closeout-report.json" in names
            assert "closeout-report.md" in names
            assert "artifact_chain.json" in names
            assert "state.json" in names
            assert "bundle_manifest.json" in names
            assert "attestation.json" in names

    def test_audit_bundle_manifest_valid(self, tmp_path):
        result, run_dir = self._invoke_audit(tmp_path)
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        with zipfile.ZipFile(zips[0], "r") as zf:
            manifest = json.loads(zf.read("bundle_manifest.json"))
        assert "bundle_id" in manifest
        assert "attestation" in manifest
        assert "content_hash" in manifest["attestation"]
        assert "bundle_hash" in manifest["attestation"]
        assert manifest["run_id"] == "paper-audit-test"

    def test_audit_attestation_valid(self, tmp_path):
        result, run_dir = self._invoke_audit(tmp_path)
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        with zipfile.ZipFile(zips[0], "r") as zf:
            att = json.loads(zf.read("attestation.json"))
        assert att["run_id"] == "paper-audit-test"
        assert att["workflow_type"] == "paper"
        assert "artifact_hashes" in att
        assert "content_hash" in att

    def test_audit_persists_manifest_alongside_zip(self, tmp_path):
        result, run_dir = self._invoke_audit(tmp_path)
        bundle_manifests = list(run_dir.glob("bundle_manifest_*.json"))
        attestations = list(run_dir.glob("attestation_*.json"))
        assert len(bundle_manifests) >= 1
        assert len(attestations) >= 1

    def test_audit_artifact_chain_binds_reports(self, tmp_path):
        result, run_dir = self._invoke_audit(tmp_path)
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        with zipfile.ZipFile(zips[0], "r") as zf:
            chain = json.loads(zf.read("artifact_chain.json"))
        names = [e["artifact"] for e in chain]
        assert "closeout-report.json" in names
        assert "closeout-report.md" in names
        assert "state.json" in names

    def test_audit_output_flag(self, tmp_path):
        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app

        run_dir, state = _make_run_dir(tmp_path, "paper-audit-out")
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# R", encoding="utf-8")

        out_zip = str(tmp_path / "custom-output.zip")
        rt = _fake_runtime(run_dir, "paper-audit-out")
        runner = CliRunner()

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"):
            result = runner.invoke(app,
                                   ["paper", "audit", "--run-id", "paper-audit-out",
                                    "--output", out_zip],
                                   catch_exceptions=False)
        assert result.exit_code == 0
        assert Path(out_zip).exists()

    def test_audit_with_omitted_evidence(self, tmp_path):
        """Unlisted files trigger omitted-evidence.json in the bundle."""
        run_dir, state = _make_run_dir(tmp_path, "paper-audit-omit")
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# R", encoding="utf-8")
        # Add an unlisted file
        (run_dir / "extra-data.json").write_text('{"extra": true}', encoding="utf-8")

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        rt = _fake_runtime(run_dir, "paper-audit-omit")
        runner = CliRunner()

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"):
            result = runner.invoke(app,
                                   ["paper", "audit", "--run-id", "paper-audit-omit"],
                                   catch_exceptions=False)
        assert result.exit_code == 0
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        with zipfile.ZipFile(zips[0], "r") as zf:
            names = zf.namelist()
            assert "omitted-evidence.json" in names
            omitted = json.loads(zf.read("omitted-evidence.json"))
            assert "extra-data.json" in omitted["omitted_files"]


# ---------------------------------------------------------------------------
# 7. Sanitize run_id protection
# ---------------------------------------------------------------------------

class TestA25SanitizeProtection:
    def test_audit_invalid_run_id(self, tmp_path):
        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app

        def bad_sanitize(rid):
            raise ValueError("invalid run_id: path traversal")

        rt = {
            "sanitize": bad_sanitize,
            "create": MagicMock(),
            "execute": MagicMock(),
            "status": MagicMock(),
            "redact": lambda s: s,
        }
        runner = CliRunner()
        with patch(_RT_PATH, return_value=rt), \
             patch("ai_workflow_hub.cli.init_env"):
            result = runner.invoke(app, ["paper", "audit", "--run-id", "../../etc/passwd"])
        assert result.exit_code == 1

    def test_audit_run_not_found(self, tmp_path):
        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app

        rt = _fake_runtime(tmp_path, "nonexistent")
        runner = CliRunner()
        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"):
            result = runner.invoke(app, ["paper", "audit", "--run-id", "nonexistent"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# 8. Content hash tamper-evidence
# ---------------------------------------------------------------------------

class TestA25TamperEvidence:
    def test_manifest_content_hash_verifiable(self, tmp_path):
        """Verify content_hash can be independently recomputed from bundle files."""
        from ai_workflow_hub.cli import _build_bundle_manifest

        files = [
            {"path": "a.json", "sha256": "hash_a", "size": 10},
            {"path": "b.json", "sha256": "hash_b", "size": 20},
        ]
        m = _build_bundle_manifest("b1", "r1", files, "t1")

        # Recompute content_hash independently
        _sorted = sorted([(f["path"], f["sha256"]) for f in files])
        expected = hashlib.sha256(
            json.dumps(_sorted, sort_keys=True).encode("utf-8")
        ).hexdigest()
        assert m["attestation"]["content_hash"] == expected

    def test_bundle_hash_binds_id_and_timestamp(self):
        from ai_workflow_hub.cli import _build_bundle_manifest
        files = [{"path": "a.json", "sha256": "h", "size": 1}]
        m = _build_bundle_manifest("b1", "r1", files, "2026-06-12T00:00:00")

        # Recompute bundle_hash independently
        expected = hashlib.sha256(json.dumps({
            "bundle_id": "b1",
            "content_hash": m["attestation"]["content_hash"],
            "timestamp": "2026-06-12T00:00:00",
            "run_id": "r1",
        }, sort_keys=True).encode("utf-8")).hexdigest()
        assert m["attestation"]["bundle_hash"] == expected
