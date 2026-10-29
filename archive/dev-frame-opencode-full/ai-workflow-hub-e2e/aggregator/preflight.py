"""Credential preflight checks for external adapters.

Distinguishes "blocked (no credentials)" from "ran but found nothing".
Blocked adapters should not count in the integrity watchdog's zero-result metric.
"""

import os

# Map adapter module names to lists of required environment variables.
# Order: the short adapter name (without "aggregator.adapters." prefix).
ADAPTER_CREDENTIALS = {
    "metersphere_adapter": ["MS_API_KEY"],
    "sentry_adapter": ["SENTRY_AUTH_TOKEN"],
    "bugly_adapter": ["BUGLY_ANDROID_APP_ID", "BUGLY_ANDROID_APP_KEY"],
    "wetest_adapter": ["WETEST_API_KEY", "WETEST_API_SECRET"],
}


def check_credentials(adapter_name: str) -> dict:
    """Check whether the named adapter has the required environment variables set.

    Args:
        adapter_name: Short adapter name, e.g. "sentry_adapter".

    Returns:
        {"ready": bool, "missing": [list of missing env var names]}.
        If the adapter is NOT in ADAPTER_CREDENTIALS, returns
        {"ready": True, "missing": []} — local-file adapters don't need credentials.
    """
    required = ADAPTER_CREDENTIALS.get(adapter_name)
    if required is None:
        return {"ready": True, "missing": []}

    missing = [var for var in required if not os.environ.get(var)]
    return {"ready": len(missing) == 0, "missing": missing}


def preflight_all() -> dict:
    """Run credential checks for every known external adapter.

    Returns:
        {adapter_name: {"ready": bool, "missing": [...]}}
    """
    return {name: check_credentials(name) for name in ADAPTER_CREDENTIALS}
