"""Unit tests for quality gate logic (orchestrator.gate).

Covers: fail-closed behaviour, table-driven rule validation across all
three gate tiers (pr / main / release), and config load error paths.
"""

import pytest
import yaml
from pathlib import Path

from orchestrator.gate import evaluate, load_gate_config


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _results(passed: int, failed: int = 0) -> list[dict]:
    return [{"status": "passed"} for _ in range(passed)] + \
           [{"status": "failed"} for _ in range(failed)]


def _load_real_rules(gate_type: str) -> dict:
    gate_path = Path(__file__).parent.parent / "config" / "gates.yaml"
    gates = yaml.safe_load(gate_path.read_text(encoding="utf-8")) or {}
    return gates.get("gates", {}).get(gate_type, {})


# ---------------------------------------------------------------------------
# fail-closed: config load errors
# ---------------------------------------------------------------------------

class TestGateConfigLoadErrors:

    def test_missing_config_fails_closed(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"_load_error": "gates.yaml not found"})
        passed, failures, _ = evaluate("pr", _results(3))
        assert not passed
        assert any("not found" in f for f in failures)

    def test_malformed_yaml_fails_closed(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"_load_error": "gates.yaml parse error"})
        passed, failures, _ = evaluate("main", _results(5))
        assert not passed
        assert any("parse error" in f for f in failures)

    def test_generic_load_error_fails_closed(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"_load_error": "permission denied"})
        passed, failures, _ = evaluate("release", _results(10))
        assert not passed
        assert any("permission denied" in f for f in failures)

    def test_empty_config_passes(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {})
        passed, _, _ = evaluate("pr", _results(1))
        assert passed


# ---------------------------------------------------------------------------
# table-driven: pass cases
# ---------------------------------------------------------------------------

PASS_CASES = [
    # PR
    ("pr", "min_evidence_count",       {"min": 1},    (1, 0), {},
     "1 result ≥ min 1"),
    ("pr", "smoke_pass_rate",          {"min": 100},  (5, 0), {},
     "5/5 pass → 100% ≥ min 100"),
    ("pr", "lint_errors",              {"max": 0},    (1, 0), {},
     "hardcoded 0 ≤ max 0"),

    # Main
    ("main", "min_evidence_count",     {"min": 5},    (5, 0), {},
     "5 results ≥ min 5"),
    ("main", "smoke_pass_rate",        {"min": 100},  (10, 0), {},
     "10/10 pass → 100% ≥ min 100"),
    ("main", "regression_pass_rate",   {"min": 95},   (10, 0), {},
     "10/10 pass → 100% ≥ min 95"),
    ("main", "critical_bugs",          {"max": 0},    (1, 0), {},
     "hardcoded 0 ≤ max 0"),

    # Release
    ("release", "min_evidence_count",       {"min": 10}, (10, 0), {},
     "10 results ≥ min 10"),
    ("release", "smoke_pass_rate",          {"min": 100}, (15, 0), {},
     "15/15 pass → 100% ≥ min 100"),
    ("release", "regression_pass_rate",     {"min": 98},  (20, 0), {},
     "20/20 pass → 100% ≥ min 98"),
    ("release", "compatibility_pass_rate",  {"min": 90},  (1, 0), {},
     "hardcoded 100 ≥ min 90"),
    ("release", "performance_regression_count", {"max": 0}, (1, 0), {},
     "hardcoded 0 ≤ max 0"),
    ("release", "security_critical_count",      {"max": 0}, (1, 0), {},
     "hardcoded 0 ≤ max 0"),
]

FAIL_CASES = [
    # PR
    ("pr", "min_evidence_count",  {"min": 1},    (0, 0), {},
     "0 results < min 1"),
    ("pr", "smoke_pass_rate",     {"min": 100},  (3, 1), {},
     "3/4 pass → 75% < min 100"),

    # Main
    ("main", "min_evidence_count",   {"min": 5},    (4, 0), {},
     "4 results < min 5"),
    ("main", "smoke_pass_rate",      {"min": 100},  (8, 2), {},
     "8/10 pass → 80% < min 100"),
    ("main", "regression_pass_rate", {"min": 95},   (9, 1), {},
     "9/10 pass → 90% < min 95"),

    # Release
    ("release", "min_evidence_count",   {"min": 10}, (9, 0), {},
     "9 results < min 10"),
    ("release", "smoke_pass_rate",      {"min": 100}, (14, 1), {},
     "14/15 pass → 93% < min 100"),
    ("release", "regression_pass_rate", {"min": 98},  (19, 1), {},
     "19/20 pass → 95% < min 98"),
]

ALWAYS_PASS_METRICS = {
    "lint_errors", "critical_bugs", "compatibility_pass_rate",
    "performance_regression_count", "security_critical_count",
}


class TestGatePassCases:
    @pytest.mark.parametrize(
        "gate_type,rule_name,spec,results_args,extra_kwargs,_desc",
        PASS_CASES,
    )
    def test_rule_passes(self, monkeypatch, gate_type, rule_name, spec,
                         results_args, extra_kwargs, _desc):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {rule_name: spec})
        p, f = results_args
        passed, failures, _ = evaluate(gate_type, _results(p, f), **extra_kwargs)
        assert passed, f"{gate_type}/{rule_name}: expected PASS, got {failures}"


class TestGateFailCases:
    @pytest.mark.parametrize(
        "gate_type,rule_name,spec,results_args,extra_kwargs,_desc",
        FAIL_CASES,
    )
    def test_rule_fails(self, monkeypatch, gate_type, rule_name, spec,
                        results_args, extra_kwargs, _desc):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {rule_name: spec})
        p, f = results_args
        passed, failures, _ = evaluate(gate_type, _results(p, f), **extra_kwargs)
        assert not passed, f"{gate_type}/{rule_name}: expected FAIL, got PASS"
        assert any(rule_name in msg for msg in failures), \
            f"expected '{rule_name}' in failures, got: {failures}"


class TestGateAlwaysPassMetrics:
    """Metrics that are hardcoded in evaluate() and always pass."""

    @pytest.mark.parametrize("rule_name,spec", [
        ("lint_errors", {"max": 0}),
        ("critical_bugs", {"max": 0}),
        ("compatibility_pass_rate", {"min": 90}),
        ("performance_regression_count", {"max": 0}),
        ("security_critical_count", {"max": 0}),
    ])
    def test_always_pass(self, monkeypatch, rule_name, spec):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {rule_name: spec})
        passed, _, _ = evaluate("pr", _results(1))
        assert passed, f"{rule_name} should always pass"


# ---------------------------------------------------------------------------
# crash rules (need crash_count kwarg)
# ---------------------------------------------------------------------------

class TestGateCrashRules:

    def test_pr_crash_count_pass(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"crash_count": {"max": 0}})
        passed, _, _ = evaluate("pr", _results(1), crash_count=0)
        assert passed

    def test_pr_crash_count_fail(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"crash_count": {"max": 0}})
        passed, failures, _ = evaluate("pr", _results(1), crash_count=2)
        assert not passed
        assert any("crash_count" in f for f in failures)

    def test_main_crash_count_pass(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"crash_count": {"max": 0}})
        passed, _, _ = evaluate("main", _results(5), crash_count=0)
        assert passed

    def test_main_crash_count_fail(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"crash_count": {"max": 0}})
        passed, failures, _ = evaluate("main", _results(5), crash_count=1)
        assert not passed

    def test_release_crash_free_rate_pass(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"crash_free_rate": {"min": 99.5}})
        passed, _, _ = evaluate("release", _results(10), crash_count=0)
        assert passed

    def test_release_crash_free_rate_fail(self, monkeypatch):
        monkeypatch.setattr("orchestrator.gate.load_gate_config",
                            lambda _gt: {"crash_free_rate": {"min": 99.5}})
        # rate = 100 - 10*0.1 = 99% < 99.5 → fail
        passed, failures, _ = evaluate("release", _results(10), crash_count=10)
        assert not passed
        assert any("crash_free_rate" in f for f in failures)


# ---------------------------------------------------------------------------
# rule count consistency
# ---------------------------------------------------------------------------

class TestGateRuleCount:

    def test_pr_rules_all_covered(self):
        rules = _load_real_rules("pr")
        pass_covered = {c[1] for c in PASS_CASES if c[0] == "pr"}
        fail_covered = {c[1] for c in FAIL_CASES if c[0] == "pr"}
        crash_covered = {"crash_count"}
        covered = pass_covered | fail_covered | crash_covered
        missing = set(rules.keys()) - covered
        assert not missing, f"PR rules not covered: {missing}"

    def test_main_rules_all_covered(self):
        rules = _load_real_rules("main")
        pass_covered = {c[1] for c in PASS_CASES if c[0] == "main"}
        fail_covered = {c[1] for c in FAIL_CASES if c[0] == "main"}
        crash_covered = {"crash_count"}
        covered = pass_covered | fail_covered | crash_covered
        missing = set(rules.keys()) - covered
        assert not missing, f"Main rules not covered: {missing}"

    def test_release_rules_all_covered(self):
        rules = _load_real_rules("release")
        pass_covered = {c[1] for c in PASS_CASES if c[0] == "release"}
        fail_covered = {c[1] for c in FAIL_CASES if c[0] == "release"}
        crash_covered = {"crash_free_rate"}
        always_covered = {"compatibility_pass_rate",
                          "performance_regression_count",
                          "security_critical_count"}
        covered = (pass_covered | fail_covered | crash_covered
                   | always_covered)
        missing = set(rules.keys()) - covered
        assert not missing, f"Release rules not covered: {missing}"


# ---------------------------------------------------------------------------
# real config loads correctly
# ---------------------------------------------------------------------------

class TestLoadGateConfig:

    def test_load_pr_returns_rules(self):
        rules = load_gate_config("pr")
        assert isinstance(rules, dict)
        assert len(rules) >= 4

    def test_load_main_returns_rules(self):
        rules = load_gate_config("main")
        assert isinstance(rules, dict)
        assert len(rules) >= 5

    def test_load_release_returns_rules(self):
        rules = load_gate_config("release")
        assert isinstance(rules, dict)
        assert len(rules) >= 7

    def test_unknown_gate_type_returns_empty(self):
        assert load_gate_config("nonexistent") == {}
