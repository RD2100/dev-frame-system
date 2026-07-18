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
import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
# Process-global connection registry: session_id -> connection record.
_CONNECTIONS: dict[str, dict[str, Any]] = {}

VALID_DECISIONS = {"allow_once", "allow_always", "deny", "revoke"}
_AUTHORIZED_SCOPE = "read_default"
MEMORY_READ_SCOPE = "obsidian_memory_read"
MEMORY_PROPOSE_SCOPE = "obsidian_memory_propose"
_PERSISTABLE_SCOPES = frozenset({_AUTHORIZED_SCOPE})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _grants_path(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir) / "mcp-connection-grants.json"


def _audit_path(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir) / "mcp-audit.jsonl"


def fingerprint(client_name: str | None) -> str:
    return hashlib.sha256(("devframe-mcp:" + (client_name or "unknown")).encode("utf-8")).hexdigest()[:16]


def _audit_hash(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


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


def audit(runtime_dir: str | Path | None, event: dict[str, Any]) -> bool:
    if runtime_dir is None:
        return False
    path = _audit_path(runtime_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": _now(), **event}, ensure_ascii=True) + "\n")
        return True
    except OSError:
        return False


def register_connection(session_id: str, client_name: str | None, *, runtime_dir: str | Path | None = None) -> dict[str, Any]:
    """Record a connection on initialize; auto-authorize if an allow-always grant exists."""
    with _LOCK:
        fp = fingerprint(client_name)
        status, scope = "pending", "none"
        scopes: list[str] = []
        authorization_source = "none"
        grant = _load_grants(runtime_dir).get(fp)
        if grant and grant.get("decision") == "allow_always" and not grant.get("revoked"):
            status, scope = "authorized", _AUTHORIZED_SCOPE
            scopes = [
                value
                for value in grant.get("scopes", [_AUTHORIZED_SCOPE])
                if value in _PERSISTABLE_SCOPES
            ] or [_AUTHORIZED_SCOPE]
            authorization_source = "persisted_grant"
        conn = {
            "connection_id": session_id,
            "client_name": client_name or "unknown",
            "fingerprint": fp,
            "status": status,
            "scope": scope,
            "scopes": scopes,
            "scope_bindings": {},
            "requested_scopes": [],
            "requested_scope_bindings": {},
            "authorization_source": authorization_source,
            "created_at": _now(),
            "updated_at": _now(),
        }
        _CONNECTIONS[session_id] = conn
        audit(runtime_dir, {
            "event": "connect",
            "connection_id": session_id,
            "client_fingerprint": fp,
            "status": status,
        })
        return dict(conn)


def ensure_connection(session_id: str, client_name: str | None = None, *, runtime_dir: str | Path | None = None) -> dict[str, Any]:
    """Return a connection, registering it pending if unseen (e.g. after restart)."""
    with _LOCK:
        existing = _CONNECTIONS.get(session_id)
        if existing is not None:
            return dict(existing)
    return register_connection(session_id, client_name, runtime_dir=runtime_dir)


def get_connection(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    with _LOCK:
        conn = _CONNECTIONS.get(session_id)
        return dict(conn) if conn else None


def is_authorized(session_id: str | None) -> bool:
    conn = get_connection(session_id)
    return bool(conn and conn.get("status") == "authorized")


def has_scope(
    session_id: str | None,
    scope: str,
    scope_binding: str = "",
) -> bool:
    conn = get_connection(session_id)
    granted = bool(
        conn
        and conn.get("status") == "authorized"
        and str(scope or "") in set(conn.get("scopes") or [])
    )
    if not granted or not scope_binding:
        return granted
    return secrets.compare_digest(
        str((conn.get("scope_bindings") or {}).get(str(scope or "")) or ""),
        str(scope_binding),
    )


def is_current_human_authorized(session_id: str | None) -> bool:
    conn = get_connection(session_id)
    return bool(
        conn
        and conn.get("status") == "authorized"
        and conn.get("authorization_source") == "current_human_decision"
    )


def request_scope(
    session_id: str | None,
    scope: str,
    scope_binding: str = "",
) -> dict[str, Any] | None:
    requested = str(scope or "").strip()
    if not session_id or not requested:
        return None
    with _LOCK:
        conn = _CONNECTIONS.get(session_id)
        if conn is None:
            return None
        values = set(conn.get("requested_scopes") or [])
        values.add(requested)
        conn["requested_scopes"] = sorted(values)
        if scope_binding:
            bindings = dict(conn.get("requested_scope_bindings") or {})
            bindings[requested] = str(scope_binding)
            conn["requested_scope_bindings"] = bindings
        conn["updated_at"] = _now()
        return dict(conn)


def list_connections() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(c) for c in _CONNECTIONS.values()]


def record_tool_call(
    session_id: str | None,
    tool: str,
    *,
    authorized: bool,
    runtime_dir: str | Path | None = None,
    required_scope: str = "",
    scope_binding: str = "",
    project_id: str = "",
    path_hashes: list[str] | None = None,
) -> bool:
    if required_scope and not has_scope(session_id, required_scope, scope_binding):
        request_scope(session_id, required_scope, scope_binding)
    conn = get_connection(session_id) or {}
    return audit(runtime_dir, {
        "event": "tool_call",
        "connection_id": session_id or "",
        "client_fingerprint": str(conn.get("fingerprint") or ""),
        "tool": tool,
        "authorized": bool(authorized),
        "required_scope": str(required_scope or ""),
        "scope_binding": str(scope_binding or ""),
        "granted_scopes": list(conn.get("scopes") or []),
        "project_id_hash": _audit_hash(project_id),
        "path_hashes": list(path_hashes or []),
    })


def record_tool_result(
    session_id: str | None,
    tool: str,
    *,
    runtime_dir: str | Path | None,
    status: str,
    project_id: str = "",
    path_hashes: list[str] | None = None,
    source_digests: list[str] | None = None,
    required_scope: str = "",
    result_count: int = 0,
) -> bool:
    conn = get_connection(session_id) or {}
    return audit(runtime_dir, {
        "event": "tool_result",
        "connection_id": session_id or "",
        "client_fingerprint": str(conn.get("fingerprint") or ""),
        "tool": str(tool or ""),
        "status": str(status or ""),
        "required_scope": str(required_scope or ""),
        "granted_scopes": list(conn.get("scopes") or []),
        "project_id_hash": _audit_hash(project_id),
        "path_hashes": list(path_hashes or []),
        "source_digests": list(source_digests or []),
        "result_count": max(0, int(result_count or 0)),
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
            conn["scopes"] = []
            conn["scope_bindings"] = {}
            conn["requested_scopes"] = []
            conn["requested_scope_bindings"] = {}
            conn["authorization_source"] = "current_human_decision"
        elif decision == "revoke":
            for active in _CONNECTIONS.values():
                if active.get("fingerprint") == conn.get("fingerprint"):
                    active["status"], active["scope"] = "revoked", "none"
                    active["scopes"] = []
                    active["scope_bindings"] = {}
                    active["requested_scopes"] = []
                    active["requested_scope_bindings"] = {}
                    active["authorization_source"] = "current_human_decision"
                    active["updated_at"] = _now()
            grants = _load_grants(runtime_dir)
            grant = grants.get(conn["fingerprint"])
            if grant is not None:
                grant["revoked"] = True
                if runtime_dir is not None:
                    _save_grants(runtime_dir, grants)
        elif decision == "allow_once":
            requested_scopes = set(conn.get("requested_scopes") or [])
            conn["status"], conn["scope"] = "authorized", _AUTHORIZED_SCOPE
            conn["scopes"] = sorted(
                {_AUTHORIZED_SCOPE, *set(conn.get("scopes") or []), *requested_scopes}
            )
            bindings = dict(conn.get("scope_bindings") or {})
            requested_bindings = dict(conn.get("requested_scope_bindings") or {})
            bindings.update(
                {
                    scope: requested_bindings[scope]
                    for scope in requested_scopes
                    if requested_bindings.get(scope)
                }
            )
            conn["scope_bindings"] = bindings
            conn["requested_scopes"] = []
            conn["requested_scope_bindings"] = {}
            conn["authorization_source"] = "current_human_decision"
        elif decision == "allow_always":
            requested_scopes = set(conn.get("requested_scopes") or [])
            conn["status"], conn["scope"] = "authorized", _AUTHORIZED_SCOPE
            conn["scopes"] = sorted(
                {_AUTHORIZED_SCOPE, *set(conn.get("scopes") or []), *requested_scopes}
            )
            bindings = dict(conn.get("scope_bindings") or {})
            requested_bindings = dict(conn.get("requested_scope_bindings") or {})
            bindings.update(
                {
                    scope: requested_bindings[scope]
                    for scope in requested_scopes
                    if requested_bindings.get(scope)
                }
            )
            conn["scope_bindings"] = bindings
            conn["requested_scopes"] = []
            conn["requested_scope_bindings"] = {}
            conn["authorization_source"] = "current_human_decision"
            if runtime_dir is not None:
                grants = _load_grants(runtime_dir)
                grants[conn["fingerprint"]] = {
                    "decision": "allow_always",
                    "client_name": conn["client_name"],
                    "granted_at": _now(),
                    "revoked": False,
                    # Sensitive scopes require a fresh human decision for every
                    # connection and are intentionally never restored by a
                    # client-name-only persistent grant.
                    "scopes": sorted(_PERSISTABLE_SCOPES),
                }
                _save_grants(runtime_dir, grants)
        conn["updated_at"] = _now()
        audit(runtime_dir, {"event": "decision", "connection_id": connection_id, "decision": decision})
        return dict(conn)


def _reset_for_tests() -> None:
    with _LOCK:
        _CONNECTIONS.clear()
