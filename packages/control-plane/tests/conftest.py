"""Shared pytest fixtures for control-plane tests."""
from __future__ import annotations

import os

import pytest


_LOOPBACK_PROXY_BYPASS_HOSTS = ("127.0.0.1", "localhost", "::1")


def _with_loopback_proxy_bypass(value: str | None) -> str:
    entries = [entry.strip() for entry in (value or "").split(",") if entry.strip()]
    seen = {entry.casefold() for entry in entries}
    for host in _LOOPBACK_PROXY_BYPASS_HOSTS:
        if host.casefold() not in seen:
            entries.append(host)
            seen.add(host.casefold())
    return ",".join(entries)


@pytest.fixture(autouse=True)
def bypass_loopback_proxy_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep local test HTTP servers off developer/system HTTP proxies."""
    for env_name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(env_name, _with_loopback_proxy_bypass(os.environ.get(env_name)))
