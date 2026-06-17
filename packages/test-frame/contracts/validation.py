# -*- coding: utf-8 -*-
"""Tool Contract v1 validation."""

import ipaddress
from urllib.parse import urlparse

from contracts.tool_contract import ToolContract, AdapterType


def validate_lifecycle_url(url: str, allowed_hosts: set[str] | None = None) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return f"lifecycle URL scheme is not allowed: {parsed.scheme or '<missing>'}"
    host = (parsed.hostname or "").lower()
    if not host:
        return "lifecycle URL host is required"
    if host in {"localhost", "localhost.localdomain"}:
        return "localhost lifecycle URL is not allowed"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        metadata_ip = ipaddress.ip_address("169.254.169.254")
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_unspecified
            or ip.is_multicast
            or ip == metadata_ip
        ):
            return f"private or local lifecycle URL host is not allowed: {host}"
    if allowed_hosts is None:
        allowed_hosts = set()
    normalized_allowed = {h.lower() for h in allowed_hosts}
    if host not in normalized_allowed:
        return f"lifecycle URL host is not allowlisted: {host}"
    return None


def validate_contract(tc: ToolContract, *, allowed_hosts: set[str] | None = None) -> list[str]:
    """Validate a ToolContract and return a list of error messages.

    Returns an empty list if the contract is valid.
    """
    errors = []

    if not tc.tool:
        errors.append("tool name is required")
    if not tc.adapter_type:
        errors.append("adapter.type is required")
    if tc.adapter_type not in _VALID_ADAPTER_TYPES:
        errors.append(
            f"Unknown adapter.type: {tc.adapter_type!r}. "
            f"Must be one of: {_VALID_ADAPTER_TYPES}"
        )

    # CLI adapters need execution config
    if tc.adapter_type == "cli_json":
        if tc.execution is None:
            errors.append("execution config is required for cli_json adapter")
        elif not tc.execution.executable:
            errors.append("execution.command.executable is required for cli_json adapter")

    # Async adapters need lifecycle config
    if tc.adapter_type in ("api_async_job", "api_platform"):
        if tc.lifecycle is None:
            errors.append("lifecycle config is required for async adapters")
        else:
            if not tc.lifecycle.submit or not tc.lifecycle.submit.url:
                errors.append("lifecycle.submit.url is required for async adapters")
            elif error := validate_lifecycle_url(tc.lifecycle.submit.url, allowed_hosts):
                errors.append(f"lifecycle.submit.url rejected: {error}")
            if tc.lifecycle.poll and tc.lifecycle.poll.url:
                if error := validate_lifecycle_url(tc.lifecycle.poll.url, allowed_hosts):
                    errors.append(f"lifecycle.poll.url rejected: {error}")
            if tc.lifecycle.download and tc.lifecycle.download.url:
                if error := validate_lifecycle_url(tc.lifecycle.download.url, allowed_hosts):
                    errors.append(f"lifecycle.download.url rejected: {error}")
            if tc.adapter_type == "api_async_job":
                if not tc.lifecycle.submit.job_id_path:
                    errors.append("lifecycle.submit.response.job_id_path is required for api_async_job")

    # Normalization config
    if tc.normalization:
        if not tc.normalization.format:
            errors.append("normalization.format is required")
        if not tc.normalization.normalizer:
            errors.append("normalization.normalizer is required")

    return errors


_VALID_ADAPTER_TYPES: set[str] = {
    "cli_json",
    "api_async_job",
    "api_platform",
    "api_issues",
    "api_crash_stats",
    "wrapper",
}
