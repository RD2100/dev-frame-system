"""Connect-time consent + connection governance for the DevFrame MCP server.

Any AI may knock (call MCP), but a connection can only USE tools after the human
explicitly authorizes it. Authorization is a local decision (Allow once / Allow
always / Deny / Revoke) recorded here; "Allow always" persists a durable grant
keyed by the client fingerprint so a returning client need not re-prompt. Every
connection event and decision is appended to a durable audit log.

This module owns ONLY the consent state + audit. It never reads project data and
never writes the workspace.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
# Process-global connection registry: session_id -> connection record.
_CONNECTIONS: dict[str, dict[str, Any]] = {}

VALID_DECISIONS = {"allow_once", "allow_always", "deny", "revoke"}
_AUTHORIZED_SCOPE = "read_default"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _grants_path(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir) / "mcp-connection-grants.json"


def _audit_path(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir) / "mcp-audit.jsonl"


def _canonical_client_info(client_info: str | dict[str, Any] | None) -> dict[str, str]:
    if isinstance(client_info, str):
        raw: dict[str, Any] = {"name": client_info}
    elif isinstance(client_info, dict):
        raw = client_info
    else:
        raw = {}
    result: dict[str, str] = {}
    for key in ("name", "title", "version"):
        value = str(raw.get(key) or "").strip()
        value = "".join(
            character
            for character in value
            if unicodedata.category(character) != "Cc"
        )
        encoded = value.encode("utf-8", errors="ignore")
        if len(encoded) > 256:
            value = encoded[:256].decode("utf-8", errors="ignore")
        result[key] = value
    if not result["name"]:
        result["name"] = "unknown"
    return result


def _has_complete_client_info(
    client_info: str | dict[str, Any] | None,
    canonical_info: dict[str, str],
) -> bool:
    return isinstance(client_info, dict) and all(
        canonical_info[key] and canonical_info[key] != "unknown"
        for key in ("name", "title", "version")
    )


def fingerprint(
    client_info: str | dict[str, Any] | None,
    *,
    trust_secret: str | None = None,
) -> str:
    """Return a v3 client-family fingerprint bound to MCP client name and token."""
    canonical_info = _canonical_client_info(client_info)
    canonical = json.dumps(
        {"name": canonical_info["name"]},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    secret = str(trust_secret or "")
    key = hashlib.sha256(
        b"devframe-mcp-client-trust-v3\0" + secret.encode("utf-8")
    ).digest()
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()[:32]


def _load_grants(runtime_dir: str | Path | None) -> dict[str, Any]:
    if runtime_dir is None:
        return {}
    path = _grants_path(runtime_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_grants(runtime_dir: str | Path, grants: dict[str, Any]) -> None:
    path = _grants_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(grants, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, path)


def audit(runtime_dir: str | Path | None, event: dict[str, Any]) -> None:
    if runtime_dir is None:
        return
    path = _audit_path(runtime_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": _now(), **event}, ensure_ascii=True) + "\n")
    except OSError:
        pass


def register_connection(
    session_id: str,
    client_info: str | dict[str, Any] | None,
    *,
    runtime_dir: str | Path | None = None,
    trust_secret: str | None = None,
) -> dict[str, Any]:
    """Record a connection on initialize; auto-authorize if an allow-always grant exists."""
    with _LOCK:
        canonical_info = _canonical_client_info(client_info)
        trust_bound = bool(str(trust_secret or ""))
        identity_complete = _has_complete_client_info(client_info, canonical_info)
        fp = fingerprint(canonical_info, trust_secret=trust_secret)
        status, scope = "pending", "none"
        grant = _load_grants(runtime_dir).get(fp)
        if (
            trust_bound
            and identity_complete
            and grant
            and grant.get("decision") == "allow_always"
            and grant.get("fingerprint_version") == 3
            and not grant.get("revoked")
        ):
            status, scope = "authorized", _AUTHORIZED_SCOPE
        conn = {
            "connection_id": session_id,
            "client_name": canonical_info["name"],
            "client_info": canonical_info,
            "fingerprint": fp,
            "fingerprint_version": 3,
            "trust_bound": trust_bound,
            "identity_complete": identity_complete,
            "status": status,
            "scope": scope,
            "created_at": _now(),
            "updated_at": _now(),
        }
        _CONNECTIONS[session_id] = conn
        audit(runtime_dir, {
            "event": "connect",
            "connection_id": session_id,
            "client_name": conn["client_name"],
            "status": status,
        })
        return dict(conn)


def ensure_connection(
    session_id: str,
    client_info: str | dict[str, Any] | None = None,
    *,
    runtime_dir: str | Path | None = None,
    trust_secret: str | None = None,
) -> dict[str, Any]:
    """Return a connection, registering it pending if unseen (e.g. after restart)."""
    with _LOCK:
        existing = _CONNECTIONS.get(session_id)
        if existing is not None:
            return dict(existing)
    return register_connection(
        session_id,
        client_info,
        runtime_dir=runtime_dir,
        trust_secret=trust_secret,
    )


def get_connection(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    with _LOCK:
        conn = _CONNECTIONS.get(session_id)
        return dict(conn) if conn else None


def is_authorized(session_id: str | None) -> bool:
    conn = get_connection(session_id)
    return bool(conn and conn.get("status") == "authorized")


def list_connections() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(c) for c in _CONNECTIONS.values()]


def record_tool_call(session_id: str | None, tool: str, *, authorized: bool, runtime_dir: str | Path | None = None) -> None:
    audit(runtime_dir, {
        "event": "tool_call",
        "connection_id": session_id or "",
        "tool": tool,
        "authorized": bool(authorized),
    })


class ConsentError(Exception):
    pass


def decide(connection_id: str, decision: str, *, runtime_dir: str | Path | None = None) -> dict[str, Any]:
    """Apply a human authorization decision to a connection."""
    if decision not in VALID_DECISIONS:
        raise ConsentError(f"invalid decision: {decision}")
    with _LOCK:
        conn = _CONNECTIONS.get(connection_id)
        if conn is None:
            raise ConsentError("unknown connection")
        if decision == "deny":
            conn["status"], conn["scope"] = "denied", "none"
        elif decision == "revoke":
            conn["status"], conn["scope"] = "revoked", "none"
            grants = _load_grants(runtime_dir)
            grant = grants.get(conn["fingerprint"])
            if grant is not None:
                grant["revoked"] = True
                if runtime_dir is not None:
                    _save_grants(runtime_dir, grants)
        elif decision == "allow_once":
            conn["status"], conn["scope"] = "authorized", _AUTHORIZED_SCOPE
        elif decision == "allow_always":
            if (
                conn.get("fingerprint_version") != 3
                or not conn.get("trust_bound")
                or not conn.get("identity_complete")
            ):
                raise ConsentError(
                    "allow_always requires complete trust-bound clientInfo"
                )
            conn["status"], conn["scope"] = "authorized", _AUTHORIZED_SCOPE
            if runtime_dir is not None:
                grants = _load_grants(runtime_dir)
                grants[conn["fingerprint"]] = {
                    "decision": "allow_always",
                    "client_name": conn["client_name"],
                    "client_info": conn["client_info"],
                    "fingerprint_version": 3,
                    "granted_at": _now(),
                    "revoked": False,
                }
                _save_grants(runtime_dir, grants)
        conn["updated_at"] = _now()
        audit(runtime_dir, {"event": "decision", "connection_id": connection_id, "decision": decision})
        return dict(conn)


def _reset_for_tests() -> None:
    with _LOCK:
        _CONNECTIONS.clear()
