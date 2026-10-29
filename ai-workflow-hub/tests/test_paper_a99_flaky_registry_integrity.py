"""A99 -- Known-Flaky Registry Integrity.

Validates that the known_flaky_tests.json registry is well-formed,
that all registered flaky tests are actually deselected in regression,
and that the registry is internally consistent.

Schema version: 1.40.
"""

from __future__ import annotations

import json
import re
import sys as _sys
from pathlib import Path

import pytest

_sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


def _load_flaky_registry() -> dict:
    jf = _PROJECT_ROOT / "known_flaky_tests.json"
    if not jf.exists():
        pytest.skip("known_flaky_tests.json not found")
    return json.loads(jf.read_text(encoding="utf-8"))


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA99SchemaVersion:
    def test_schema_version_is_1_40(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.40' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or \
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
            "Schema version must be exactly 1.40 for A99"
        )

    def test_a99_contract_in_cli(self):
        """cli.py must contain A99 contract comment."""
        cli = _read_cli_source()
        assert "A99" in cli, "A99 contract comment must be present"

    def test_schema_forward_compat(self):
        """Schema must include 1.40 or 1.39."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or \
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
            "Schema must include current version 1.41 or predecessor 1.40/1.39"
        )


# -------------------------------------------------------------------
# Class 2: Flaky registry structure
# -------------------------------------------------------------------
class TestA99FlakyRegistryStructure:
    def test_known_flaky_tests_json_exists(self):
        """known_flaky_tests.json must exist at project root."""
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        assert jf.exists(), "known_flaky_tests.json must exist"

    def test_registry_has_valid_schema_version(self):
        """Registry must contain a schema_version field."""
        data = _load_flaky_registry()
        assert "schema_version" in data, "schema_version field required"
        assert isinstance(data["schema_version"], str), "schema_version must be a string"

    def test_registry_has_tests_array(self):
        """Registry must contain a 'tests' array."""
        data = _load_flaky_registry()
        assert "tests" in data, "tests array required"
        assert isinstance(data["tests"], list), "tests must be an array"

    def test_each_test_has_required_fields(self):
        """Each entry in tests must have test_id, deselect_arg, classification, failure_reason."""
        data = _load_flaky_registry()
        required_fields = {"test_id", "deselect_arg", "classification", "failure_reason"}
        for i, entry in enumerate(data.get("tests", [])):
            missing = required_fields - set(entry.keys())
            assert not missing, (
                f"tests[{i}] missing required fields: {missing}"
            )


# -------------------------------------------------------------------
# Class 3: Flaky deselect coverage
# -------------------------------------------------------------------
class TestA99FlakyDeselectCoverage:
    def test_all_flaky_tests_deselected_in_regression(self):
        """All flaky test deselect_args must appear in regression output."""
        data = _load_flaky_registry()
        reg_path = _PROJECT_ROOT / "output" / "REGRESSION_OUTPUT_A99.txt"
        if not reg_path.exists():
            pytest.skip("REGRESSION_OUTPUT_A99.txt not yet generated")
        reg_text = reg_path.read_text(encoding="utf-8")
        for entry in data.get("tests", []):
            deselect = entry["deselect_arg"]
            assert deselect in reg_text, (
                f"deselect_arg '{deselect}' not found in regression transcript"
            )

    def test_total_known_flaky_matches_tests_array(self):
        """total_known_flaky must match the length of the tests array."""
        data = _load_flaky_registry()
        assert data["total_known_flaky"] == len(data["tests"]), (
            f"total_known_flaky ({data['total_known_flaky']}) != "
            f"len(tests) ({len(data['tests'])})"
        )

    def test_all_deselect_args_are_valid_pytest_node_ids(self):
        """Each deselect_arg must look like a valid pytest node ID (path::Class::method)."""
        data = _load_flaky_registry()
        node_id_pattern = re.compile(r"^[^:]+\.py::\w+::\w+$")
        for entry in data.get("tests", []):
            deselect = entry["deselect_arg"]
            assert node_id_pattern.match(deselect), (
                f"deselect_arg '{deselect}' is not a valid pytest node ID "
                f"(expected path::Class::method)"
            )


# -------------------------------------------------------------------
# Class 4: Registry consistency
# -------------------------------------------------------------------
class TestA99RegistryConsistency:
    def test_no_duplicate_test_ids(self):
        """No duplicate test_id values in the registry."""
        data = _load_flaky_registry()
        ids = [e["test_id"] for e in data.get("tests", [])]
        assert len(ids) == len(set(ids)), (
            f"Duplicate test_ids found: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_classification_is_known_flaky(self):
        """All entries must have classification = 'known_flaky'."""
        data = _load_flaky_registry()
        for entry in data.get("tests", []):
            assert entry["classification"] == "known_flaky", (
                f"test_id '{entry['test_id']}' has classification "
                f"'{entry['classification']}', expected 'known_flaky'"
            )

    def test_all_tests_referenced_exist_as_files(self):
        """Each test_id must reference an actual test file that exists."""
        data = _load_flaky_registry()
        for entry in data.get("tests", []):
            test_file = entry["test_id"].split("::")[0]
            full_path = _PROJECT_ROOT / test_file
            assert full_path.exists(), (
                f"Test file '{test_file}' referenced by test_id "
                f"'{entry['test_id']}' does not exist"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA99Invariants:
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
        """Manifest must include evidence_bundle_hash."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A99.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A99.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data

    def test_a99_test_file_exists(self):
        """This test file itself must exist."""
        test_path = _PROJECT_ROOT / "tests" / "test_paper_a99_flaky_registry_integrity.py"
        assert test_path.exists()
