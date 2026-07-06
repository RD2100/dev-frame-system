"""P2-3: browser transport adapter boundary validator.

Per design-coverage-gap-remediation-plan.md:274-291:

  - manual mode cannot be reported as automated success;
  - experimental adapters cannot satisfy stable browser evidence;
  - Firefox is not described as CDP-compatible.

Repair strategy:
  1. Define a transport adapter schema.
  2. Keep Chrome/CDP stable first.
  3. Add Edge/Chromium CDP probes only after adapter schema tests pass.
  4. Treat WebDriver BiDi as experimental until it passes the same submit,
     wait, extract, and evidence tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Stable adapters: only Chrome CDP is stable by default.
# Edge CDP becomes stable only after adapter schema tests pass.
STABLE_ADAPTERS: tuple[str, ...] = (
    "chrome_cdp",
)

# Adapters that are explicitly experimental until proven.
EXPERIMENTAL_ADAPTERS: tuple[str, ...] = (
    "webdriver_bidi",
    "edge_cdp",
)

# All recognized adapters.
KNOWN_ADAPTERS: tuple[str, ...] = (
    "chrome_cdp",
    "edge_cdp",
    "webdriver_bidi",
    "playwright",
)

# Adapters that use CDP-compatible protocol.
# Firefox is NOT CDP-compatible (per acceptance criterion).
CDP_COMPATIBLE_ADAPTERS: tuple[str, ...] = (
    "chrome_cdp",
    "edge_cdp",
)

# Browsers that are NOT CDP-compatible.
NON_CDP_BROWSERS: tuple[str, ...] = ("firefox",)

# Recognized maturity levels.
ADAPTER_MATURITY_LEVELS: tuple[str, ...] = (
    "stable",
    "experimental",
    "waiting",
)

# Recognized execution modes.
VALID_MODES: tuple[str, ...] = (
    "automated",
    "manual",
    "hybrid",
)

# Modes that are NOT automated.
NON_AUTOMATED_MODES: tuple[str, ...] = ("manual", "hybrid")


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


# ---------------------------------------------------------------------------
# Shared helpers — validate and derive use the same functions.
# ---------------------------------------------------------------------------


def _is_valid_session_shape(
    session: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base structural check only — fields exist, values in known sets.

    True only when:
      - id, adapter, maturity, mode, browser all non-empty
      - adapter is a known adapter
      - maturity is a recognized level
      - mode is a recognized mode
    """
    errors: list[str] = []
    sid = session.get("id", "")
    prefix = f"session[{sid or '<missing>'}]"

    for field in ("id", "adapter", "maturity", "mode", "browser"):
        if not session.get(field):
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    adapter = session.get("adapter", "")
    maturity = session.get("maturity", "")
    mode = session.get("mode", "")

    if adapter not in KNOWN_ADAPTERS:
        if collect_errors:
            errors.append(
                f"{prefix}: adapter={adapter!r} is not a known adapter; "
                f"must be one of {KNOWN_ADAPTERS}"
            )
        else:
            return False, errors

    if maturity not in ADAPTER_MATURITY_LEVELS:
        if collect_errors:
            errors.append(
                f"{prefix}: maturity={maturity!r} not in {ADAPTER_MATURITY_LEVELS}"
            )
        else:
            return False, errors

    if mode not in VALID_MODES:
        if collect_errors:
            errors.append(
                f"{prefix}: mode={mode!r} not in {VALID_MODES}"
            )
        else:
            return False, errors

    return True, errors


def _check_boundary_rules(
    session: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Boundary rule checks — rules that make a session invalid as evidence.

    True only when:
      - mode is automated (manual/hybrid ≠ automated success)
      - adapter is not experimental (unless promoted to stable)
      - firefox is not described as CDP-compatible
    """
    errors: list[str] = []
    sid = session.get("id", "")
    prefix = f"session[{sid or '<missing>'}]"
    adapter = session.get("adapter", "")
    maturity = session.get("maturity", "")
    mode = session.get("mode", "")
    browser = session.get("browser", "")

    if mode in NON_AUTOMATED_MODES:
        if collect_errors:
            errors.append(
                f"{prefix}: mode={mode!r} cannot be reported as automated "
                f"success; manual/hybrid sessions are not automated evidence"
            )
        else:
            return False, errors

    if adapter in EXPERIMENTAL_ADAPTERS and maturity != "stable":
        if collect_errors:
            errors.append(
                f"{prefix}: adapter={adapter!r} is experimental; "
                f"experimental adapters cannot satisfy stable browser evidence. "
                f"Promote to maturity='stable' only after adapter schema tests pass."
            )
        else:
            return False, errors

    if maturity == "stable" and adapter not in STABLE_ADAPTERS and adapter not in EXPERIMENTAL_ADAPTERS:
        if collect_errors:
            errors.append(
                f"{prefix}: adapter={adapter!r} is not approved for stable evidence; "
                f"only adapters in STABLE_ADAPTERS or EXPERIMENTAL_ADAPTERS "
                f"(when promoted) can provide stable evidence"
            )
        else:
            return False, errors

    if browser in NON_CDP_BROWSERS and adapter in CDP_COMPATIBLE_ADAPTERS:
        if collect_errors:
            errors.append(
                f"{prefix}: browser={browser!r} is not CDP-compatible; "
                f"cannot use CDP adapter={adapter!r}"
            )
        else:
            return False, errors

    return True, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_transport_boundary(payload: dict) -> ValidationResult:
    """Validate browser transport sessions against boundary rules.

    Enforces:
      - Stable evidence only from stable adapters in automated mode
      - Firefox is not CDP-compatible
      - Manual/hybrid mode is not automated success
      - Experimental adapters are not stable evidence
    """
    errors: list[str] = []
    sessions: list[dict] = payload.get("browser_sessions") or []

    for session in sessions:
        _, shape_errors = _is_valid_session_shape(session, collect_errors=True)
        errors.extend(shape_errors)
        _, boundary_errors = _check_boundary_rules(session, collect_errors=True)
        errors.extend(boundary_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_transport_boundary(payload: dict) -> dict:
    """Read-only projection of browser transport adapter usage.

    Returns counts by maturity, browser, and adapter.
    Invalid sessions (empty id, unknown adapter, etc.) are excluded.
    """
    sessions: list[dict] = payload.get("browser_sessions") or []

    stable_count = 0
    experimental_count = 0
    waiting_count = 0
    by_browser: dict[str, dict] = {}
    by_adapter: dict[str, dict] = {}

    for session in sessions:
        shape_ok, _ = _is_valid_session_shape(session, collect_errors=False)
        if not shape_ok:
            continue

        maturity = session.get("maturity", "")
        browser = session.get("browser", "")
        adapter = session.get("adapter", "")

        if maturity == "stable":
            stable_count += 1
        elif maturity == "experimental":
            experimental_count += 1
        elif maturity == "waiting":
            waiting_count += 1

        if browser not in by_browser:
            by_browser[browser] = {"browser": browser, "count": 0}
        by_browser[browser]["count"] += 1

        if adapter not in by_adapter:
            by_adapter[adapter] = {"adapter": adapter, "count": 0}
        by_adapter[adapter]["count"] += 1

    return {
        "total_sessions": stable_count + experimental_count + waiting_count,
        "stable_count": stable_count,
        "experimental_count": experimental_count,
        "waiting_count": waiting_count,
        "by_browser": by_browser,
        "by_adapter": by_adapter,
    }
