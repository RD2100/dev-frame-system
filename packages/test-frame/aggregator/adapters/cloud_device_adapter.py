"""Cloud device matrix contract helpers.

This adapter intentionally handles only local request/response shapes. It does
not call BrowserStack, Firebase Test Lab, Maestro Cloud, or any other provider.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_PROVIDERS = {"browserstack", "firebase-test-lab", "maestro-cloud", "fake"}
BLOCKED_PROVIDER_STATUSES = {
    "auth_missing",
    "capacity_unavailable",
    "no_device_capacity",
    "quota_exceeded",
}
FAILED_PROVIDER_STATUSES = {"cancelled", "error", "failed", "timeout"}
PASSED_PROVIDER_STATUSES = {"passed", "success"}
PENDING_PROVIDER_STATUSES = {"queued", "running"}


def validate_matrix_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a local cloud device matrix request."""
    if not isinstance(payload, dict):
        raise ValueError("cloud device matrix must be a JSON object")

    provider = str(payload.get("provider") or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported cloud device provider: {provider or '<missing>'}")

    devices = payload.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ValueError("cloud device matrix must contain non-empty devices")

    tests = payload.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("cloud device matrix must contain non-empty tests")

    return {
        "provider": provider,
        "device_count": len(devices),
        "test_count": len(tests),
    }


def normalize_provider_status(status: str) -> str:
    """Normalize provider-specific device status into TestFrame status."""
    normalized = (status or "").strip().lower().replace("-", "_")
    if normalized in PASSED_PROVIDER_STATUSES:
        return "passed"
    if normalized in BLOCKED_PROVIDER_STATUSES or normalized in PENDING_PROVIDER_STATUSES:
        return "blocked"
    if normalized in FAILED_PROVIDER_STATUSES:
        return "failed"
    return "failed"


def normalize_matrix_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a local cloud device matrix response into result rows."""
    if not isinstance(response, dict):
        raise ValueError("cloud device response must be a JSON object")
    devices = response.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ValueError("cloud device response must contain non-empty devices")

    provider = str(response.get("provider") or "unknown")
    matrix_id = str(response.get("matrix_id") or "")
    results: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            raise ValueError("cloud device response device entries must be objects")
        device_name = str(device.get("name") or device.get("model") or "unknown")
        status = normalize_provider_status(str(device.get("status") or ""))
        error_text = str(device.get("error") or device.get("reason") or "")
        results.append(
            {
                "test_name": f"[{device_name}] cloud device matrix",
                "status": status,
                "tool": "cloud_device",
                "duration_ms": int(device.get("duration_ms") or 0),
                "metadata": {
                    "provider": provider,
                    "matrix_id": matrix_id,
                    "device": device_name,
                    "os_version": str(device.get("os_version") or ""),
                },
                "error": {"message": error_text} if status != "passed" and error_text else None,
            }
        )
    return results
