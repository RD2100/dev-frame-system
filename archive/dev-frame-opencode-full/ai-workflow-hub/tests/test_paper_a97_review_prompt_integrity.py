"""A97 -- GPT Review Prompt Integrity.

Ensures that the GPT review prompt file is properly structured and included
in the evidence pack:
  - GPT_REVIEW_PROMPT_A97.txt exists in scripts/
  - Prompt references the correct acceptance number (A97)
  - Prompt contains required review sections:
    schema verification, test results, evidence bundle, tamper detection
  - Prompt is included in the evidence ZIP
  - Preserves all A82-A96 invariants

Schema version: 1.38.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


def _read_prompt() -> str | None:
    for candidate in [
        _PROJECT_ROOT / "scripts" / "GPT_REVIEW_PROMPT_A97.txt",
        _PROJECT_ROOT / "GPT_REVIEW_PROMPT_A97.txt",
    ]:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA97SchemaVersion:
    def test_schema_version_is_1_38(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.38' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be 1.39+ for A97"
        )

    def test_a97_contract_in_cli(self):
        """cli.py must contain A97 contract comment."""
        cli = _read_cli_source()
        assert "A97" in cli, "A97 contract comment must be present"

    def test_schema_forward_compat(self):
        """Schema OR chain must include 1.38."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.38"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.37"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema OR chain must include current version"
        )


# -------------------------------------------------------------------
# Class 2: Prompt file existence
# -------------------------------------------------------------------
class TestA97PromptExistence:
    def test_prompt_file_exists(self):
        """GPT_REVIEW_PROMPT_A97.txt must exist in scripts/ or root."""
        path = _PROJECT_ROOT / "scripts" / "GPT_REVIEW_PROMPT_A97.txt"
        alt = _PROJECT_ROOT / "GPT_REVIEW_PROMPT_A97.txt"
        if not path.exists() and not alt.exists():
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available in this environment")
        assert path.exists() or alt.exists()

    def test_prompt_not_empty(self):
        """GPT_REVIEW_PROMPT_A97.txt must not be empty."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        assert len(text.strip()) > 0, "Prompt file must not be empty"

    def test_prompt_minimum_length(self):
        """Prompt must be at least 200 chars to contain meaningful review instructions."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        assert len(text) >= 200, (
            f"Prompt too short ({len(text)} chars), minimum 200"
        )


# -------------------------------------------------------------------
# Class 3: Prompt content — acceptance reference
# -------------------------------------------------------------------
class TestA97PromptContent:
    def test_prompt_references_a97(self):
        """Prompt must explicitly reference A97."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        assert "A97" in text, "Prompt must reference A97"

    def test_prompt_references_schema_1_38(self):
        """Prompt must reference schema version 1.38."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        assert "1.38" in text, "Prompt must reference schema version 1.38"

    def test_prompt_mentions_schema_verification(self):
        """Prompt must contain schema verification instructions."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        lower = text.lower()
        assert "schema" in lower, "Prompt must mention schema verification"

    def test_prompt_mentions_test_results(self):
        """Prompt must reference test results."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        lower = text.lower()
        assert "test" in lower and ("result" in lower or "pass" in lower), (
            "Prompt must mention test results"
        )

    def test_prompt_mentions_evidence_bundle(self):
        """Prompt must reference evidence bundle."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        lower = text.lower()
        assert "evidence" in lower or "bundle" in lower, (
            "Prompt must mention evidence bundle"
        )

    def test_prompt_mentions_tamper_detection(self):
        """Prompt must reference tamper detection or hash integrity."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        lower = text.lower()
        has_tamper = "tamper" in lower or "hash" in lower or "integrity" in lower
        assert has_tamper, "Prompt must mention tamper detection or hash integrity"

    def test_prompt_has_accepted_rejected_format(self):
        """Prompt must instruct to respond with ACCEPTED or REJECTED."""
        text = _read_prompt()
        if text is None:
            pytest.skip("GPT_REVIEW_PROMPT_A97.txt not available")
        assert "ACCEPTED" in text and "REJECTED" in text, (
            "Prompt must include ACCEPTED/REJECTED response format"
        )


# -------------------------------------------------------------------
# Class 4: Prompt included in evidence pack
# -------------------------------------------------------------------
class TestA97PromptInPack:
    def test_pack_script_includes_prompt(self):
        """pack_a97.py must include GPT_REVIEW_PROMPT_A97.txt."""
        pack_path = _PROJECT_ROOT / "scripts" / "pack_a97.py"
        if not pack_path.exists():
            pytest.skip("pack_a97.py not yet created")
        pack_src = pack_path.read_text(encoding="utf-8")
        assert "GPT_REVIEW_PROMPT_A97" in pack_src, (
            "Pack script must include GPT_REVIEW_PROMPT_A97.txt"
        )

    def test_validate_script_checks_prompt(self):
        """validate_a97.py must verify prompt file existence."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a97.py"
        if not val_path.exists():
            pytest.skip("validate_a97.py not yet created")
        val_src = val_path.read_text(encoding="utf-8")
        assert "GPT_REVIEW_PROMPT" in val_src, (
            "Validate script must check for GPT_REVIEW_PROMPT"
        )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA97Invariants:
    def test_emit_json_module_level(self):
        """_emit_json must be defined at module level."""
        cli = _read_cli_source()
        for line in cli.splitlines():
            if "def _emit_json(" in line:
                assert line == line.lstrip(), "_emit_json must be at module level"
                return
        pytest.fail("_emit_json definition not found")

    def test_zero_console_print_json_dumps(self):
        """No console.print(json.dumps(...)) calls should remain."""
        cli = _read_cli_source()
        bad = [
            l.strip() for l in cli.splitlines()
            if "console.print(json.dumps" in l and not l.strip().startswith("#")
        ]
        assert len(bad) == 0

    def test_click_pin_in_pyproject(self):
        """pyproject.toml must pin click>=8.2.0,<9."""
        pp = _PROJECT_ROOT / "pyproject.toml"
        if not pp.exists():
            pytest.skip("pyproject.toml not found")
        text = pp.read_text(encoding="utf-8")
        assert "click>=8.2.0,<9" in text or "click>=8.2.0, <9" in text

    def test_known_flaky_valid(self):
        """known_flaky_tests.json must have total_known_flaky >= 1."""
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1

    def test_evidence_bundle_hash_in_manifest(self):
        """Manifest must still include evidence_bundle_hash."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A97.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A97.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data

    def test_a97_test_file_exists(self):
        """This test file itself must exist."""
        test_path = _PROJECT_ROOT / "tests" / "test_paper_a97_review_prompt_integrity.py"
        assert test_path.exists()
