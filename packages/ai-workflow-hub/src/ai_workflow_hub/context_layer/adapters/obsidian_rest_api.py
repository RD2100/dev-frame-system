"""Obsidian Local REST API helpers for scoped paper workflows.

The adapter talks to the community Local REST API plugin on loopback. It never
persists or returns API tokens, note bodies, or absolute vault paths.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

DEFAULT_BASE_URL = "https://127.0.0.1:27124"
DEFAULT_TOKEN_ENV = "OBSIDIAN_REST_API_KEY"
PROFILE = "paper_obsidian_rest_probe_report"
SYNC_PLAN_PROFILE = "paper_obsidian_rest_sync_plan_report"
SCHEMA_VERSION = "1.0"
MANAGED_BLOCK_START = "<!-- devframe:paper-metadata:start -->"
MANAGED_BLOCK_END = "<!-- devframe:paper-metadata:end -->"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_base_url(base_url: str) -> str:
    value = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    return value or DEFAULT_BASE_URL


def _vault_path(relative_path: str) -> str:
    clean = relative_path.replace("\\", "/").strip("/")
    parts = [part for part in clean.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("invalid_vault_relative_path")
    return quote("/".join(parts), safe="/")


def _error_name(exc: Exception) -> str:
    return type(exc).__name__


class ObsidianRestClient:
    """Tiny wrapper around Obsidian Local REST API.

    ``http_client`` is injectable for tests and must expose
    ``request(method, url, **kwargs)``.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        token: str = "",
        verify_tls: bool = False,
        timeout: float = 10.0,
        http_client: Any | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.token = token
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.http_client = http_client

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str = DEFAULT_BASE_URL,
        token_env: str = DEFAULT_TOKEN_ENV,
        verify_tls: bool = False,
        timeout: float = 10.0,
        http_client: Any | None = None,
    ) -> "ObsidianRestClient":
        return cls(
            base_url=base_url,
            token=os.environ.get(token_env, ""),
            verify_tls=verify_tls,
            timeout=timeout,
            http_client=http_client,
        )

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        client = self.http_client
        if client is None:
            import httpx

            client = httpx
        url = f"{self.base_url}{path}"
        return client.request(
            method,
            url,
            content=content,
            headers=self._headers(headers),
            timeout=self.timeout,
            verify=self.verify_tls,
        )

    def service_status(self) -> Any:
        return self._request("GET", "/")

    def auth_check(self) -> Any:
        return self._request("GET", "/vault/.devframe-probe/auth-check-do-not-create.md")

    def write_note(self, relative_path: str, content: str) -> Any:
        return self._request(
            "PUT",
            f"/vault/{_vault_path(relative_path)}",
            content=content,
            headers={"Content-Type": "text/markdown; charset=utf-8"},
        )

    def open_note(self, relative_path: str) -> Any:
        return self._request("POST", f"/open/{_vault_path(relative_path)}")

    def read_note(self, relative_path: str) -> Any:
        return self._request("GET", f"/vault/{_vault_path(relative_path)}")


def _status_from_code(code: int, *, ok_codes: set[int]) -> str:
    if code in ok_codes:
        return "PASS"
    if code in {401, 403}:
        return "FAILED_AUTH"
    return "FAILED_RUNTIME"


def _http_status(response: Any) -> int:
    return int(getattr(response, "status_code", 0) or 0)


def build_obsidian_rest_probe_report(
    *,
    base_url: str = DEFAULT_BASE_URL,
    token_env: str = DEFAULT_TOKEN_ENV,
    token: str = "",
    verify_tls: bool = False,
    timeout: float = 10.0,
    write_probe: bool = False,
    probe_path: str = "_devframe/obsidian-rest-probe.md",
    open_probe: bool = False,
    http_client: Any | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    resolved_token = token or os.environ.get(token_env, "")
    client = ObsidianRestClient(
        base_url=base_url,
        token=resolved_token,
        verify_tls=verify_tls,
        timeout=timeout,
        http_client=http_client,
    )

    result: dict[str, Any] = {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "base_url": client.base_url,
        "token_env": token_env,
        "token_present": bool(resolved_token),
        "token_persisted": False,
        "verify_tls": verify_tls,
        "service_status": "NOT_RUN",
        "auth_status": "NOT_RUN",
        "write_status": "NOT_RUN",
        "open_status": "NOT_RUN",
        "mcp_endpoint": f"{client.base_url}/mcp/",
        "reasons": [],
    }

    try:
        response = client.service_status()
        result["service_status"] = _status_from_code(_http_status(response), ok_codes={200})
    except Exception as exc:
        result["service_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"service:{_error_name(exc)}")
        result["overall_status"] = "FAILED_RUNTIME"
        return result

    if not resolved_token:
        result["auth_status"] = "BLOCKED_MISSING_TOKEN"
        result["overall_status"] = "BLOCKED_MISSING_TOKEN"
        return result

    try:
        response = client.auth_check()
        status_code = _http_status(response)
        result["auth_status"] = "PASS" if status_code in {200, 404} else _status_from_code(
            status_code,
            ok_codes={200, 404},
        )
    except Exception as exc:
        result["auth_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"auth:{_error_name(exc)}")

    if write_probe and result["auth_status"] == "PASS":
        try:
            content = "\n".join([
                "---",
                'schema_type: "devframe_obsidian_rest_probe"',
                f"generated_at: \"{generated}\"",
                "---",
                "",
                "# DevFrame Obsidian REST Probe",
                "",
                "This note was created by a scoped Local REST API probe.",
                "",
            ])
            response = client.write_note(probe_path, content)
            result["write_status"] = _status_from_code(_http_status(response), ok_codes={200, 201, 204})
        except Exception as exc:
            result["write_status"] = "FAILED_RUNTIME"
            result["reasons"].append(f"write:{_error_name(exc)}")

    if open_probe and result["auth_status"] == "PASS":
        try:
            response = client.open_note(probe_path)
            result["open_status"] = _status_from_code(_http_status(response), ok_codes={200, 204})
        except Exception as exc:
            result["open_status"] = "FAILED_RUNTIME"
            result["reasons"].append(f"open:{_error_name(exc)}")

    statuses = [
        result["service_status"],
        result["auth_status"],
        result["write_status"] if write_probe else "PASS",
        result["open_status"] if open_probe else "PASS",
    ]
    result["overall_status"] = "PASS" if all(status == "PASS" for status in statuses) else "FAILED_RUNTIME"
    return result


def sync_markdown_files_to_obsidian_rest(
    *,
    files: list[tuple[str, Path]],
    base_url: str = DEFAULT_BASE_URL,
    token_env: str = DEFAULT_TOKEN_ENV,
    token: str = "",
    verify_tls: bool = False,
    timeout: float = 10.0,
    open_relative_path: str = "",
    http_client: Any | None = None,
) -> dict[str, Any]:
    resolved_token = token or os.environ.get(token_env, "")
    summary: dict[str, Any] = {
        "status": "NOT_RUN",
        "base_url": _normalize_base_url(base_url),
        "token_env": token_env,
        "token_present": bool(resolved_token),
        "token_persisted": False,
        "write_count": 0,
        "open_called": False,
        "error_count": 0,
        "first_error": "",
    }
    if not resolved_token:
        summary["status"] = "BLOCKED_MISSING_TOKEN"
        summary["first_error"] = "missing_token"
        return summary

    client = ObsidianRestClient(
        base_url=base_url,
        token=resolved_token,
        verify_tls=verify_tls,
        timeout=timeout,
        http_client=http_client,
    )
    for relative_path, local_path in files:
        try:
            text = local_path.read_text(encoding="utf-8")
            response = client.write_note(relative_path, text)
            if _http_status(response) not in {200, 201, 204}:
                raise RuntimeError(f"http_status_{_http_status(response)}")
            summary["write_count"] += 1
        except Exception as exc:
            summary["error_count"] += 1
            if not summary["first_error"]:
                summary["first_error"] = _error_name(exc)

    if open_relative_path:
        try:
            response = client.open_note(open_relative_path)
            if _http_status(response) in {200, 204}:
                summary["open_called"] = True
            else:
                raise RuntimeError(f"http_status_{_http_status(response)}")
        except Exception as exc:
            summary["error_count"] += 1
            if not summary["first_error"]:
                summary["first_error"] = _error_name(exc)

    summary["status"] = "PASS" if summary["error_count"] == 0 else "FAILED_RUNTIME"
    return summary


def _compute_fingerprint(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content or "")


def _managed_block(text: str) -> str:
    start = text.find(MANAGED_BLOCK_START)
    end = text.find(MANAGED_BLOCK_END)
    if start < 0 or end < 0 or end < start:
        return ""
    return text[start:end + len(MANAGED_BLOCK_END)]


def _safe_path_reject(relative_path: str) -> None:
    _vault_path(relative_path)


def build_obsidian_rest_sync_plan_report(
    *,
    local_path: Path,
    remote_relative_path: str,
    base_url: str = DEFAULT_BASE_URL,
    token_env: str = DEFAULT_TOKEN_ENV,
    token: str = "",
    verify_tls: bool = False,
    timeout: float = 10.0,
    http_client: Any | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    resolved_token = token or os.environ.get(token_env, "")
    result: dict[str, Any] = {
        "profile": SYNC_PLAN_PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "mode": "sync_plan",
        "base_url": _normalize_base_url(base_url),
        "remote_relative_path": remote_relative_path,
        "local_path_fingerprint": _compute_fingerprint(str(local_path)),
        "token_present": bool(resolved_token),
        "token_persisted": False,
        "body_persisted": False,
        "remote_body_persisted": False,
        "plan_status": "NOT_RUN",
        "plan_action": "BLOCKED",
        "remote_status": "NOT_RUN",
        "local": {
            "exists": False,
            "fingerprint": "",
            "char_count": 0,
            "managed_block_present": False,
            "managed_fingerprint": "",
        },
        "remote": {
            "exists": False,
            "fingerprint": "",
            "char_count": 0,
            "managed_block_present": False,
            "managed_fingerprint": "",
        },
        "reasons": [],
    }

    try:
        _safe_path_reject(remote_relative_path)
    except ValueError:
        result["plan_status"] = "BLOCKED_INVALID_REMOTE_PATH"
        result["reasons"].append("invalid_remote_path")
        return result

    if not local_path.exists() or not local_path.is_file():
        result["plan_status"] = "BLOCKED_LOCAL_MISSING"
        result["reasons"].append("local_file_not_found")
        return result

    result["local"]["exists"] = True
    if not resolved_token:
        result["plan_status"] = "BLOCKED_MISSING_TOKEN"
        result["reasons"].append("missing_token")
        return result

    try:
        local_text = local_path.read_text(encoding="utf-8")
    except Exception as exc:
        result["plan_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"local_read:{_error_name(exc)}")
        return result

    local_managed = _managed_block(local_text)
    result["local"]["char_count"] = len(local_text)
    result["local"]["fingerprint"] = _compute_fingerprint(local_text)
    result["local"]["managed_block_present"] = bool(local_managed)
    result["local"]["managed_fingerprint"] = _compute_fingerprint(local_managed) if local_managed else ""

    client = ObsidianRestClient(
        base_url=base_url,
        token=resolved_token,
        verify_tls=verify_tls,
        timeout=timeout,
        http_client=http_client,
    )

    try:
        response = client.read_note(remote_relative_path)
        status_code = _http_status(response)
        if status_code == 404:
            result["remote_status"] = "MISSING"
            result["plan_status"] = "PLAN_CREATE_REMOTE"
            result["plan_action"] = "CREATE_REMOTE"
            result["reasons"].append("remote_note_not_found")
            return result
        if status_code in {401, 403}:
            result["remote_status"] = "FAILED_AUTH"
            result["plan_status"] = "FAILED_AUTH"
            result["reasons"].append("remote_auth_failed")
            return result
        if status_code not in {200}:
            result["remote_status"] = "FAILED_RUNTIME"
            result["plan_status"] = "FAILED_RUNTIME"
            result["reasons"].append(f"remote_read_http_{status_code}")
            return result
        remote_text = _response_text(response)
    except Exception as exc:
        result["remote_status"] = "FAILED_RUNTIME"
        result["plan_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"remote_read:{_error_name(exc)}")
        return result

    remote_managed = _managed_block(remote_text)
    result["remote_status"] = "PASS"
    result["remote"]["exists"] = True
    result["remote"]["char_count"] = len(remote_text)
    result["remote"]["fingerprint"] = _compute_fingerprint(remote_text)
    result["remote"]["managed_block_present"] = bool(remote_managed)
    result["remote"]["managed_fingerprint"] = _compute_fingerprint(remote_managed) if remote_managed else ""

    if result["local"]["fingerprint"] == result["remote"]["fingerprint"]:
        result["plan_status"] = "PASS_NOOP"
        result["plan_action"] = "NOOP"
        result["conflict"] = False
    elif local_managed and remote_managed and local_managed == remote_managed:
        result["plan_status"] = "PLAN_PRESERVE_REMOTE_USER_CONTENT"
        result["plan_action"] = "PRESERVE_REMOTE_USER_CONTENT"
        result["conflict"] = False
    elif local_managed and remote_managed:
        result["plan_status"] = "PLAN_UPDATE_REMOTE_MANAGED_BLOCK"
        result["plan_action"] = "UPDATE_REMOTE_MANAGED_BLOCK"
        result["conflict"] = False
    else:
        result["plan_status"] = "CONFLICT_UNMANAGED_NOTE"
        result["plan_action"] = "REQUIRE_MANUAL_REVIEW"
        result["conflict"] = True
        result["reasons"].append("managed_block_missing")

    return result



build_sync_plan_report = build_obsidian_rest_sync_plan_report

APPLY_PROFILE = "paper_obsidian_rest_sync_apply_report"


def _replace_managed_block(remote_text: str, local_managed: str) -> str:
    start = remote_text.find(MANAGED_BLOCK_START)
    end = remote_text.find(MANAGED_BLOCK_END)
    before = remote_text[:start]
    after = remote_text[end + len(MANAGED_BLOCK_END):]
    return before + local_managed + after


def build_obsidian_rest_sync_apply_report(
    *,
    local_path: Path,
    remote_relative_path: str,
    base_url: str = DEFAULT_BASE_URL,
    token_env: str = DEFAULT_TOKEN_ENV,
    token: str = "",
    verify_tls: bool = False,
    timeout: float = 10.0,
    http_client: Any | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    resolved_token = token or os.environ.get(token_env, "")
    result: dict[str, Any] = {
        "profile": APPLY_PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "mode": "sync_apply",
        "base_url": _normalize_base_url(base_url),
        "remote_relative_path": remote_relative_path,
        "local_path_fingerprint": _compute_fingerprint(str(local_path)),
        "token_present": bool(resolved_token),
        "token_persisted": False,
        "body_persisted": False,
        "remote_body_persisted": False,
        "apply_status": "NOT_RUN",
        "apply_action": "BLOCKED",
        "remote_status": "NOT_RUN",
        "local": {
            "exists": False,
            "fingerprint": "",
            "char_count": 0,
            "managed_block_present": False,
            "managed_fingerprint": "",
        },
        "remote": {
            "exists": False,
            "fingerprint": "",
            "char_count": 0,
            "managed_block_present": False,
            "managed_fingerprint": "",
        },
        "reasons": [],
    }

    try:
        _safe_path_reject(remote_relative_path)
    except ValueError:
        result["apply_status"] = "BLOCKED_INVALID_REMOTE_PATH"
        result["reasons"].append("invalid_remote_path")
        return result

    if not local_path.exists() or not local_path.is_file():
        result["apply_status"] = "BLOCKED_LOCAL_MISSING"
        result["reasons"].append("local_file_not_found")
        return result

    result["local"]["exists"] = True
    if not resolved_token:
        result["apply_status"] = "BLOCKED_MISSING_TOKEN"
        result["reasons"].append("missing_token")
        return result

    try:
        local_text = local_path.read_text(encoding="utf-8")
    except Exception as exc:
        result["apply_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"local_read:{_error_name(exc)}")
        return result

    local_managed = _managed_block(local_text)
    result["local"]["char_count"] = len(local_text)
    result["local"]["fingerprint"] = _compute_fingerprint(local_text)
    result["local"]["managed_block_present"] = bool(local_managed)
    result["local"]["managed_fingerprint"] = _compute_fingerprint(local_managed) if local_managed else ""

    client = ObsidianRestClient(
        base_url=base_url,
        token=resolved_token,
        verify_tls=verify_tls,
        timeout=timeout,
        http_client=http_client,
    )

    try:
        response = client.read_note(remote_relative_path)
        status_code = _http_status(response)
    except Exception as exc:
        result["remote_status"] = "FAILED_RUNTIME"
        result["apply_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"remote_read:{_error_name(exc)}")
        return result

    if status_code == 404:
        try:
            response = client.write_note(remote_relative_path, local_text)
            write_code = _http_status(response)
            if write_code not in {200, 201, 204}:
                result["apply_status"] = "FAILED_RUNTIME"
                result["reasons"].append(f"create_http_{write_code}")
                return result
        except Exception as exc:
            result["apply_status"] = "FAILED_RUNTIME"
            result["reasons"].append(f"create:{_error_name(exc)}")
            return result
        result["remote_status"] = "CREATED"
        result["apply_status"] = "APPLIED_CREATE"
        result["apply_action"] = "CREATED_REMOTE"
        return result

    if status_code in {401, 403}:
        result["remote_status"] = "FAILED_AUTH"
        result["apply_status"] = "FAILED_AUTH"
        result["reasons"].append("remote_auth_failed")
        return result
    if status_code != 200:
        result["remote_status"] = "FAILED_RUNTIME"
        result["apply_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"remote_read_http_{status_code}")
        return result

    remote_text = _response_text(response)
    remote_managed = _managed_block(remote_text)
    result["remote_status"] = "PASS"
    result["remote"]["exists"] = True
    result["remote"]["char_count"] = len(remote_text)
    result["remote"]["fingerprint"] = _compute_fingerprint(remote_text)
    result["remote"]["managed_block_present"] = bool(remote_managed)
    result["remote"]["managed_fingerprint"] = _compute_fingerprint(remote_managed) if remote_managed else ""

    if not local_managed or not remote_managed:
        result["apply_status"] = "BLOCKED_UNMANAGED_NOTE"
        result["apply_action"] = "REQUIRE_MANUAL_REVIEW"
        result["reasons"].append("managed_block_missing")
        return result

    if local_managed == remote_managed:
        result["apply_status"] = "PASS_NOOP"
        result["apply_action"] = "NOOP"
        return result

    merged = _replace_managed_block(remote_text, local_managed)
    try:
        response = client.write_note(remote_relative_path, merged)
        write_code = _http_status(response)
        if write_code not in {200, 201, 204}:
            result["apply_status"] = "FAILED_RUNTIME"
            result["reasons"].append(f"update_http_{write_code}")
            return result
    except Exception as exc:
        result["apply_status"] = "FAILED_RUNTIME"
        result["reasons"].append(f"update:{_error_name(exc)}")
        return result

    result["apply_status"] = "APPLIED_UPDATE"
    result["apply_action"] = "UPDATED_MANAGED_BLOCK"
    return result


build_sync_apply_report = build_obsidian_rest_sync_apply_report
