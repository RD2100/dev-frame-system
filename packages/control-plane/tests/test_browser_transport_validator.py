"""Tests for P2-3: browser transport adapter boundary validator.

Per design-coverage-gap-remediation-plan.md:274-291:
  - manual mode cannot be reported as automated success;
  - experimental adapters cannot satisfy stable browser evidence;
  - Firefox is not described as CDP-compatible.
"""
from __future__ import annotations

import pytest

from control_plane.browser_transport_validator import (
    ADAPTER_MATURITY_LEVELS,
    CDP_COMPATIBLE_ADAPTERS,
    EXPERIMENTAL_ADAPTERS,
    STABLE_ADAPTERS,
    derive_transport_boundary,
    validate_transport_boundary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session(**overrides):
    """Minimal valid browser session entry."""
    base = {
        "id": "sess-1",
        "project_id": "proj-1",
        "adapter": "chrome_cdp",
        "maturity": "stable",
        "mode": "automated",
        "browser": "chrome",
    }
    base.update(overrides)
    return base


def _payload(sessions=None):
    return {"browser_sessions": sessions or []}


# ---------------------------------------------------------------------------
# Adapter maturity and CDP compatibility
# ---------------------------------------------------------------------------

class TestAdapterMaturity:
    def test_stable_adapter_automated_ok(self):
        sess = _session(adapter="chrome_cdp", maturity="stable", mode="automated")
        result = validate_transport_boundary(_payload([sess]))
        assert result.valid is True

    def test_experimental_cannot_satisfy_stable_evidence(self):
        """Acceptance: experimental adapters cannot satisfy stable browser evidence."""
        sess = _session(
            adapter="webdriver_bidi", maturity="experimental",
            mode="automated",
        )
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "experimental" in result.errors[0].lower()
        assert "cannot" in result.errors[0].lower()

    def test_edge_cdp_experimental_by_default(self):
        """Edge/CDP starts experimental — does not satisfy stable evidence."""
        sess = _session(
            adapter="edge_cdp", maturity="experimental", mode="automated",
        )
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "experimental" in result.errors[0].lower()

    def test_edge_cdp_promoted_to_stable_ok(self):
        """Edge/CDP promoted to stable after adapter schema tests pass."""
        sess = _session(adapter="edge_cdp", maturity="stable", mode="automated")
        result = validate_transport_boundary(_payload([sess]))
        assert result.valid is True

    def test_waiting_adapter_is_not_automated_stable(self):
        """Waiting is a valid maturity — not automated, not counted as stable."""
        sess = _session(adapter="chrome_cdp", maturity="waiting")
        result = validate_transport_boundary(_payload([sess]))
        assert result.valid is True
        proj = derive_transport_boundary(_payload([sess]))
        assert proj["stable_count"] == 0
        assert proj["waiting_count"] == 1


# ---------------------------------------------------------------------------
# Manual mode cannot be reported as automated success
# ---------------------------------------------------------------------------

class TestManualMode:
    def test_manual_mode_cannot_be_automated_success(self):
        """Acceptance: manual mode cannot be reported as automated success."""
        sess = _session(adapter="chrome_cdp", mode="manual")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "manual" in result.errors[0].lower()
        assert "automated" in result.errors[0].lower()

    def test_automated_mode_ok(self):
        sess = _session(mode="automated")
        result = validate_transport_boundary(_payload([sess]))
        assert result.valid is True

    def test_hybrid_mode_not_automated(self):
        sess = _session(mode="hybrid")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "hybrid" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# Firefox is not CDP-compatible
# ---------------------------------------------------------------------------

class TestFirefoxCompatibility:
    def test_firefox_not_cdp_compatible(self):
        """Acceptance: Firefox is not described as CDP-compatible."""
        sess = _session(
            adapter="firefox_cdp", browser="firefox",
        )
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "firefox" in result.errors[0].lower()
        assert "cdp" in result.errors[0].lower()

    def test_firefox_cannot_use_cdp_adapter(self):
        """Firefox browser with any cdp-like adapter is rejected."""
        sess = _session(adapter="chrome_cdp", browser="firefox")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "firefox" in result.errors[0].lower()

    def test_firefox_with_trailing_space_cannot_use_cdp_adapter(self):
        """Firefox with surrounding whitespace is still rejected for CDP."""
        sess = _session(adapter="chrome_cdp", browser="firefox ")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        errors = " ".join(result.errors).lower()
        assert "firefox" in errors
        assert "cdp" in errors

    def test_firefox_with_non_cdp_adapter_ok(self):
        """Firefox with webdriver_bidi is OK for CDP check, but still blocked by
        experimental maturity."""
        sess = _session(
            adapter="webdriver_bidi", browser="firefox", maturity="experimental",
        )
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "experimental" in " ".join(result.errors).lower()

    def test_chrome_with_cdp_ok(self):
        sess = _session(adapter="chrome_cdp", browser="chrome")
        result = validate_transport_boundary(_payload([sess]))
        assert result.valid is True

    def test_edge_with_cdp_ok(self):
        sess = _session(adapter="edge_cdp", browser="edge")
        result = validate_transport_boundary(_payload([sess]))
        assert result.valid is True


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_missing_id(self):
        sess = _session(id="")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "id" in result.errors[0]

    def test_missing_adapter(self):
        sess = _session(adapter="")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "adapter" in result.errors[0]

    def test_missing_maturity(self):
        sess = _session(maturity="")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "maturity" in result.errors[0]

    def test_missing_mode(self):
        sess = _session(mode="")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "mode" in result.errors[0]

    def test_missing_browser(self):
        sess = _session(browser="")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "browser" in result.errors[0]

    def test_whitespace_required_strings_fail(self):
        sess = _session(id="   ", adapter="\t", maturity="\n", mode=" ", browser=" \t ")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert any("id is required" in e for e in result.errors)
        assert any("adapter is required" in e for e in result.errors)
        assert any("maturity is required" in e for e in result.errors)
        assert any("mode is required" in e for e in result.errors)
        assert any("browser is required" in e for e in result.errors)
        assert derive_transport_boundary(_payload([sess]))["total_sessions"] == 0

    def test_invalid_maturity_level(self):
        sess = _session(maturity="unknown_level")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "unknown_level" in result.errors[0]

    def test_invalid_mode(self):
        sess = _session(mode="semi_auto")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "semi_auto" in result.errors[0]

    def test_invalid_adapter(self):
        sess = _session(adapter="nonexistent_adapter")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "nonexistent_adapter" in result.errors[0]


# ---------------------------------------------------------------------------
# derive_transport_boundary (projection)
# ---------------------------------------------------------------------------

class TestDeriveTransportBoundary:
    def test_empty_payload(self):
        result = derive_transport_boundary({})
        assert result["total_sessions"] == 0
        assert result["stable_count"] == 0
        assert result["claimed_stable_count"] == 0
        assert result["valid_stable_count"] == 0
        assert result["experimental_count"] == 0

    def test_counts_by_maturity(self):
        sessions = [
            _session(id="s1", maturity="stable"),
            _session(id="s2", maturity="stable"),
            _session(id="s3", maturity="experimental", adapter="webdriver_bidi"),
            _session(id="s4", maturity="waiting"),
        ]
        result = derive_transport_boundary(_payload(sessions))
        assert result["total_sessions"] == 4
        assert result["stable_count"] == 2
        assert result["claimed_stable_count"] == 2
        assert result["valid_stable_count"] == 2
        assert result["experimental_count"] == 1
        assert result["waiting_count"] == 1

    def test_invalid_sessions_not_counted(self):
        sessions = [_session(id="")]  # no id → invalid
        result = derive_transport_boundary(_payload(sessions))
        assert result["total_sessions"] == 0

    def test_boundary_invalid_stable_sessions_are_not_valid_evidence(self):
        sessions = [
            _session(id="manual-chrome", adapter="chrome_cdp", maturity="stable",
                     mode="manual"),
            _session(id="playwright-stable", adapter="playwright",
                     maturity="stable", mode="automated"),
            _session(id="valid-chrome", adapter="chrome_cdp", maturity="stable",
                     mode="automated"),
        ]
        validation = validate_transport_boundary(_payload(sessions))
        assert not validation.valid

        result = derive_transport_boundary(_payload(sessions))
        assert result["total_sessions"] == 3
        assert result["claimed_stable_count"] == 3
        assert result["stable_count"] == 1
        assert result["valid_stable_count"] == 1

    def test_by_browser(self):
        sessions = [
            _session(id="s1", browser="chrome"),
            _session(id="s2", browser="chrome"),
            _session(id="s3", browser="edge"),
            _session(id="s4", browser="firefox", adapter="webdriver_bidi",
                     maturity="experimental"),
        ]
        result = derive_transport_boundary(_payload(sessions))
        assert result["by_browser"]["chrome"]["count"] == 2
        assert result["by_browser"]["edge"]["count"] == 1
        assert result["by_browser"]["firefox"]["count"] == 1

    def test_by_adapter(self):
        sessions = [
            _session(id="s1", adapter="chrome_cdp"),
            _session(id="s2", adapter="chrome_cdp"),
            _session(id="s3", adapter="edge_cdp"),
        ]
        result = derive_transport_boundary(_payload(sessions))
        assert result["by_adapter"]["chrome_cdp"]["count"] == 2
        assert result["by_adapter"]["edge_cdp"]["count"] == 1

    def test_projection_read_only(self):
        result = derive_transport_boundary(
            _payload([_session()])
        )
        assert "errors" not in result
        assert "_internal" not in result
        assert "raw_sessions" not in result
        assert "decisions" not in result


# ---------------------------------------------------------------------------
# Edge/CDP probe gating
# ---------------------------------------------------------------------------

class TestEdgeCdpProbeGating:
    def test_edge_cdp_only_stable_after_probe_tests(self):
        """Edge/CDP probes should only be accepted after adapter schema tests
        pass — i.e., when maturity=stable."""
        sess = _session(adapter="edge_cdp", maturity="experimental")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid

        sess2 = _session(adapter="edge_cdp", maturity="stable")
        result2 = validate_transport_boundary(_payload([sess2]))
        assert result2.valid is True


# ---------------------------------------------------------------------------
# WebDriver BiDi experimental
# ---------------------------------------------------------------------------

class TestWebDriverBiDi:
    def test_webdriver_bidi_experimental(self):
        """WebDriver BiDi is experimental — cannot satisfy stable evidence."""
        sess = _session(adapter="webdriver_bidi", maturity="experimental")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid

    def test_webdriver_bidi_promoted_to_stable_is_ok(self):
        """Once WebDriver BiDi passes submit/wait/extract/evidence tests,
        it can be promoted to stable."""
        sess = _session(adapter="webdriver_bidi", maturity="stable")
        result = validate_transport_boundary(_payload([sess]))
        assert result.valid is True


# ---------------------------------------------------------------------------
# Stable adapter invariant
# ---------------------------------------------------------------------------

class TestStableAdapterInvariants:
    def test_only_chrome_cdp_is_stable_by_default(self):
        """Chrome CDP is the only adapter stable by default."""
        assert "chrome_cdp" in STABLE_ADAPTERS
        assert "webdriver_bidi" not in STABLE_ADAPTERS
        assert "edge_cdp" not in STABLE_ADAPTERS
        assert "firefox_cdp" not in STABLE_ADAPTERS
        assert "playwright" not in STABLE_ADAPTERS

    def test_firefox_cdp_not_in_cdp_compatible(self):
        assert "firefox_cdp" not in CDP_COMPATIBLE_ADAPTERS

    def test_experimental_adapters_are_known(self):
        """WebDriver BiDi is explicitly experimental."""
        assert "webdriver_bidi" in EXPERIMENTAL_ADAPTERS

    def test_playwright_not_stable_evidence_by_default(self):
        """Playwright is KNOWN but not stable/experimental — cannot claim stable."""
        sess = _session(adapter="playwright", maturity="stable", mode="automated")
        result = validate_transport_boundary(_payload([sess]))
        assert not result.valid
        assert "playwright" in result.errors[0].lower()
        assert "stable" in result.errors[0].lower()

    def test_projection_counts_playwright_shape_but_validator_rejects_stable(self):
        """Projection counts shape-valid playwright sessions, but validator rejects
        stable evidence from unapproved adapter."""
        sessions = [
            _session(id="s1", adapter="playwright", maturity="stable",
                     mode="automated"),
            _session(id="s2", adapter="chrome_cdp", maturity="stable",
                     mode="automated"),
        ]
        result = validate_transport_boundary(_payload(sessions))
        assert not result.valid
        assert "playwright" in result.errors[0].lower()

        proj = derive_transport_boundary(_payload(sessions))
        assert proj["total_sessions"] == 2
        assert proj["claimed_stable_count"] == 2
        assert proj["stable_count"] == 1
        assert proj["valid_stable_count"] == 1
