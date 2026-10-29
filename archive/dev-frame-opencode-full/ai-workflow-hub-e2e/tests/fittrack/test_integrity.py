"""Test adapter integrity watchdog — no real API calls, mock-only."""

import sys
import pytest
from aggregator.collector import collect_all_results, compute_integrity, _ADAPTERS, _adapter_status


# ---- helpers ----

def _build_mock_adapter(results: list[dict]):
    """Return a callable collect(project_config=None) -> results."""
    def collect(project_config=None):
        return list(results)
    return collect


def _build_mock_module(collect_fn, name="mock"):
    """Return a fake module object whose .collect is collect_fn."""
    import types
    mod = types.ModuleType(name)
    mod.collect = collect_fn
    return mod


def _inject_mock_modules(modules: list, monkeypatch: pytest.MonkeyPatch):
    """Register mock modules in sys.modules and set _ADAPTERS to their names."""
    names = [f"mock_adapter_{i}" for i in range(len(modules))]
    for name, mod in zip(names, modules):
        sys.modules[name] = mod
    monkeypatch.setattr("aggregator.collector._ADAPTERS", list(names))


def _cleanup_mock_modules(names: list):
    """Remove mock modules from sys.modules."""
    for name in names:
        sys.modules.pop(name, None)


class TestAllAdaptersWorking:
    """Test 1: All adapters work normally -> no warning."""

    def test_all_adapters_return_results(self, monkeypatch):
        names = ["mock_adapter_0", "mock_adapter_1", "mock_adapter_2"]
        adapters = [
            _build_mock_module(_build_mock_adapter([{"test_name": "t1", "status": "passed", "tool": "tool1"}]), names[0]),
            _build_mock_module(_build_mock_adapter([{"test_name": "t2", "status": "passed", "tool": "tool2"}]), names[1]),
            _build_mock_module(_build_mock_adapter([{"test_name": "t3", "status": "passed", "tool": "tool3"}]), names[2]),
        ]
        _inject_mock_modules(adapters, monkeypatch)
        try:
            results = collect_all_results()
            integrity = compute_integrity()
            assert len(results) == 3
            assert integrity["total_adapters"] == 3
            assert integrity["zero_result_adapters"] == []
            assert integrity["error_adapters"] == []
            assert integrity["warning"] is False
            assert integrity["message"] == ""
        finally:
            _cleanup_mock_modules(names)


class TestMajorityZeroResults:
    """Test 2: 3 of 5 adapters return 0 results (60%) -> warning generated."""

    def test_majority_zero_results_triggers_warning(self, monkeypatch):
        sample = [{"test_name": "t", "status": "passed", "tool": "t"}]
        names = ["mock_adapter_0", "mock_adapter_1", "mock_adapter_2", "mock_adapter_3", "mock_adapter_4"]
        adapters = [
            _build_mock_module(_build_mock_adapter(sample), names[0]),
            _build_mock_module(_build_mock_adapter(sample), names[1]),
            _build_mock_module(_build_mock_adapter([]), names[2]),
            _build_mock_module(_build_mock_adapter([]), names[3]),
            _build_mock_module(_build_mock_adapter([]), names[4]),
        ]
        _inject_mock_modules(adapters, monkeypatch)
        try:
            results = collect_all_results()
            integrity = compute_integrity()
            assert len(results) == 2
            assert integrity["total_adapters"] == 5
            assert len(integrity["zero_result_adapters"]) == 3
            assert len(integrity["error_adapters"]) == 0
            assert integrity["warning"] is True
            assert "INTEGRITY WARNING" in integrity["message"]
            assert "3 adapters returned 0 results" in integrity["message"]
        finally:
            _cleanup_mock_modules(names)


class TestMinorityError:
    """Test 3: 1 of 5 adapters errors -> no warning (below 50%)."""

    def test_single_error_no_warning(self, monkeypatch):
        sample = [{"test_name": "t", "status": "passed", "tool": "t"}]
        names = ["mock_adapter_0", "mock_adapter_1", "mock_adapter_2", "mock_adapter_3", "mock_adapter_4"]

        def _failing_collect(project_config=None):
            raise RuntimeError("boom")

        adapters = [
            _build_mock_module(_build_mock_adapter(sample), names[0]),
            _build_mock_module(_build_mock_adapter(sample), names[1]),
            _build_mock_module(_build_mock_adapter(sample), names[2]),
            _build_mock_module(_build_mock_adapter(sample), names[3]),
            _build_mock_module(_failing_collect, names[4]),
        ]
        _inject_mock_modules(adapters, monkeypatch)
        try:
            results = collect_all_results()
            integrity = compute_integrity()
            assert len(results) == 4
            assert integrity["total_adapters"] == 5
            assert len(integrity["zero_result_adapters"]) == 0
            assert len(integrity["error_adapters"]) == 1
            assert integrity["warning"] is False
            assert integrity["message"] == ""
        finally:
            _cleanup_mock_modules(names)


class TestAllAdaptersError:
    """Test 4: All adapters error -> warning generated."""

    def test_all_adapters_error_triggers_warning(self, monkeypatch):
        def _failing_collect(project_config=None):
            raise RuntimeError("boom")

        names = ["mock_adapter_0", "mock_adapter_1", "mock_adapter_2"]
        adapters = [
            _build_mock_module(_failing_collect, names[0]),
            _build_mock_module(_failing_collect, names[1]),
            _build_mock_module(_failing_collect, names[2]),
        ]
        _inject_mock_modules(adapters, monkeypatch)
        try:
            results = collect_all_results()
            integrity = compute_integrity()
            assert len(results) == 0
            assert integrity["total_adapters"] == 3
            assert len(integrity["zero_result_adapters"]) == 0
            assert len(integrity["error_adapters"]) == 3
            assert integrity["warning"] is True
            assert "INTEGRITY WARNING" in integrity["message"]
            assert "3 adapters errored" in integrity["message"]
        finally:
            _cleanup_mock_modules(names)


class TestBackwardCompatibility:
    """summary.json without integrity field should be safely readable."""

    def test_missing_integrity_field_is_safe(self):
        import json
        old_summary = {
            "total": 100,
            "passed": 90,
            "failed": 10,
            "pass_rate": 90.0,
            "by_tool": {"pytest": {"total": 100, "passed": 90, "failed": 10}},
            "generated_at": "2025-01-01T00:00:00",
        }
        integrity = old_summary.get("integrity", {})
        assert integrity == {}
        dumped = json.dumps(old_summary)
        loaded = json.loads(dumped)
        assert "integrity" not in loaded


class TestMixedZeroAndError:
    """Test 5: Mixed zero-results + errors across the 50% threshold -> warning."""

    def test_mixed_zero_and_error_triggers_warning(self, monkeypatch):
        sample = [{"test_name": "t", "status": "passed", "tool": "t"}]

        def _failing_collect(project_config=None):
            raise RuntimeError("boom")

        names = ["mock_adapter_0", "mock_adapter_1", "mock_adapter_2", "mock_adapter_3"]
        adapters = [
            _build_mock_module(_build_mock_adapter(sample), names[0]),
            _build_mock_module(_build_mock_adapter([]), names[1]),          # zero
            _build_mock_module(_failing_collect, names[2]),                  # error
            _build_mock_module(_build_mock_adapter([]), names[3]),          # zero
        ]
        _inject_mock_modules(adapters, monkeypatch)
        try:
            results = collect_all_results()
            integrity = compute_integrity()
            assert len(results) == 1
            assert integrity["total_adapters"] == 4
            # 2 zero + 1 error = 3 silent out of 4 (75%), > 50%, so warning
            assert len(integrity["zero_result_adapters"]) == 2
            assert len(integrity["error_adapters"]) == 1
            assert integrity["warning"] is True
            assert "INTEGRITY WARNING" in integrity["message"]
        finally:
            _cleanup_mock_modules(names)
