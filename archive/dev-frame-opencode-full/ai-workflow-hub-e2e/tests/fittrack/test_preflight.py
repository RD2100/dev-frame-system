"""Test credential preflight — minimal env-var checking, no real API calls."""

import os
import sys
import pytest

from aggregator.preflight import check_credentials, preflight_all, ADAPTER_CREDENTIALS


# ---- Test 1: Local adapter (maestro) has no credential requirement ----

def test_local_adapter_no_requirement():
    """Maestro reads local files — no env vars needed."""
    result = check_credentials("maestro_adapter")
    assert result["ready"] is True
    assert result["missing"] == []


# ---- Test 2: External adapter with all env vars set ----

def test_external_adapter_ready(monkeypatch):
    """When all required env vars are set, ready=True."""
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("SENTRY_ORG", "fake-org")
    monkeypatch.setenv("SENTRY_PROJECT", "fake-proj")
    result = check_credentials("sentry_adapter")
    assert result["ready"] is True
    assert result["missing"] == []


# ---- Test 3: External adapter with missing env vars ----

def test_external_adapter_blocked(monkeypatch):
    """When required env vars are missing, ready=False with the missing list."""
    # Ensure env vars are NOT set
    monkeypatch.delenv("MS_API_KEY", raising=False)
    result = check_credentials("metersphere_adapter")
    assert result["ready"] is False
    assert "MS_API_KEY" in result["missing"]


def test_external_adapter_partial_creds(monkeypatch):
    """When only some required vars are set, still not ready."""
    monkeypatch.setenv("BUGLY_ANDROID_APP_ID", "fake-id")
    monkeypatch.delenv("BUGLY_ANDROID_APP_KEY", raising=False)
    result = check_credentials("bugly_adapter")
    assert result["ready"] is False
    assert "BUGLY_ANDROID_APP_KEY" in result["missing"]
    assert "BUGLY_ANDROID_APP_ID" not in result["missing"]


# ---- Test 4: Unknown adapter — default to ready ----

def test_unknown_adapter_ready():
    """Adapters not in ADAPTER_CREDENTIALS are assumed local and ready."""
    result = check_credentials("some_future_adapter")
    assert result["ready"] is True
    assert result["missing"] == []


# ---- Test 5: preflight_all() returns dict for all known adapters ----

def test_preflight_all_coverage():
    """preflight_all covers every adapter in ADAPTER_CREDENTIALS."""
    all_results = preflight_all()
    assert set(all_results.keys()) == set(ADAPTER_CREDENTIALS.keys())
    for name, result in all_results.items():
        assert "ready" in result
        assert "missing" in result
        assert isinstance(result["ready"], bool)
        assert isinstance(result["missing"], list)


# ---- Test 6: Blocked adapter not counted as zero_result in integrity ----

def test_blocked_adapter_not_zero_result(monkeypatch):
    """Blocked adapters are excluded from zero_result and from the >50% warning calc."""
    import types
    from aggregator.collector import (
        collect_all_results, compute_integrity,
        _ADAPTERS, _adapter_status, _blocked_adapters, _blocked_reasons,
    )

    # Build mock modules: 2 local (return results), 3 external (2 blocked, 1 works)
    local1 = types.ModuleType("mock_local_1")
    local1.collect = lambda pc=None: [{"test_name": "t1", "status": "passed", "tool": "maestro"}]
    local2 = types.ModuleType("mock_local_2")
    local2.collect = lambda pc=None: []  # zero results, but local adapter

    external1 = types.ModuleType("mock_ext_1")  # will be blocked by preflight
    external1.collect = lambda pc=None: [{"test_name": "t2", "status": "passed", "tool": "sentry"}]
    external2 = types.ModuleType("mock_ext_2")  # will be blocked by preflight
    external2.collect = lambda pc=None: [{"test_name": "t3", "status": "passed", "tool": "bugly"}]
    external3 = types.ModuleType("mock_ext_3")  # has creds, returns results
    external3.collect = lambda pc=None: [{"test_name": "t4", "status": "passed", "tool": "wetest"}]

    mock_names = ["mock_local_1", "mock_local_2", "mock_ext_1", "mock_ext_2", "mock_ext_3"]
    modules_map = {
        "mock_local_1": local1, "mock_local_2": local2,
        "mock_ext_1": external1, "mock_ext_2": external2, "mock_ext_3": external3,
    }
    for name in mock_names:
        sys.modules[name] = modules_map[name]

    # Monkeypatch the preflight check so ext_1/ext_2 are blocked, ext_3 is ready
    original_check = None
    try:
        import aggregator.preflight as pf_mod
        original_check = pf_mod.check_credentials

        def mock_check(short_name: str) -> dict:
            if short_name == "mock_ext_1":
                return {"ready": False, "missing": ["SENTRY_AUTH_TOKEN"]}
            if short_name == "mock_ext_2":
                return {"ready": False, "missing": ["BUGLY_ANDROID_APP_ID"]}
            return {"ready": True, "missing": []}

        monkeypatch.setattr("aggregator.preflight.check_credentials", mock_check)
        monkeypatch.setattr("aggregator.collector.check_credentials", mock_check)

        # Replace _ADAPTERS with our mock adapter list
        mock_full_names = [f"mock_{n}" if "mock" not in n else n for n in mock_names]
        monkeypatch.setattr("aggregator.collector._ADAPTERS", mock_full_names)

        results = collect_all_results()
        integrity = compute_integrity()

        # blocked adapters should NOT be called — results should only be from local1 + ext3 (2 results)
        assert len(results) == 2

        # zero_result_adapters should only include mock_local_2 (returned [])
        assert len(integrity["zero_result_adapters"]) == 1
        assert any("mock_local_2" in z for z in integrity["zero_result_adapters"])

        # blocked_adapters should include both mock_ext_1 and mock_ext_2
        assert len(integrity["blocked_adapters"]) == 2
        assert any("mock_ext_1" in b for b in integrity["blocked_adapters"])
        assert any("mock_ext_2" in b for b in integrity["blocked_adapters"])

        # Error should be empty
        assert len(integrity["error_adapters"]) == 0

        # eligible = 5 total - 2 blocked = 3; silent = 1 zero (local2); 1/3 = 33% < 50%, no warning
        assert integrity["warning"] is False

        # blocked_reasons should contain reasons
        assert "mock_ext_1" in integrity["blocked_reasons"] or any(
            "mock_ext_1" in k for k in integrity["blocked_reasons"]
        )
        assert "mock_ext_2" in integrity["blocked_reasons"] or any(
            "mock_ext_2" in k for k in integrity["blocked_reasons"]
        )

    finally:
        # Cleanup
        for name in mock_names:
            sys.modules.pop(name, None)
        _adapter_status.clear()
        _blocked_adapters.clear()
        _blocked_reasons.clear()
