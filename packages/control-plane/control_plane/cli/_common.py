"""Shared CLI helpers used across multiple devframe command domains."""
from __future__ import annotations

import ipaddress

from ._usage import HELP_TEXT


def _wants_help(args: list[str]) -> bool:
    return any(arg in {"-h", "--help", "help"} for arg in args)


def _print_help() -> None:
    print(HELP_TEXT.rstrip())


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
