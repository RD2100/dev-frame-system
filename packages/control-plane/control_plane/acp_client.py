"""ACP (Agent Client Protocol) transport seam (M2, slice 0).

A thin, DevFrame-owned Python transport that speaks the Agent Client Protocol's
wire format: newline-delimited JSON-RPC 2.0 over a child process's stdin/stdout
(verified: agentclientprotocol.com/protocol/transports — messages are delimited
by `\n` and MUST NOT contain embedded newlines).

Scope (recon-receipt-acp-backbone.md): this is the transport + handshake seam,
NOT yet a live OpenCode/Gemini driver and NOT yet wrapped in DevFrame governance.
It exists so later slices can drive real agents uniformly and map ACP's
permission/fs requests onto DevFrame gates. It is verified against a mock ACP
agent; no live agent and no tokens are involved.

Stdlib only (subprocess/threading/json): no new dependency, and DevFrame must own
this seam so the governance integration (gates) can live here later (reuse-002).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

# ACP protocol version this seam targets. The handshake negotiates it.
ACP_PROTOCOL_VERSION = 1

# Type aliases for client-side handlers of agent-initiated requests/notifications
# (e.g. session/update, fs/read_text_file, session/request_permission).
RequestHandler = Callable[[dict[str, Any]], dict[str, Any]]
NotificationHandler = Callable[[dict[str, Any]], None]


class AcpError(Exception):
    """A JSON-RPC error returned by the agent, or a transport failure."""


def _resolve_launch(command: list[str]) -> list[str]:
    """Resolve the executable and wrap Windows shim launchers.

    On Windows an agent like `opencode` is distributed as a `.CMD`/`.bat`/`.ps1`
    shim that `CreateProcess` cannot launch directly from a list, so resolve it
    via PATH and route shims through their interpreter. POSIX paths pass through.
    """
    executable = command[0]
    resolved = shutil.which(executable) or executable
    rest = command[1:]
    lower = resolved.lower()
    if os.name == "nt":
        if lower.endswith((".cmd", ".bat")):
            return ["cmd", "/c", resolved, *rest]
        if lower.endswith(".ps1"):
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved, *rest]
    return [resolved, *rest]


@dataclass
class _Pending:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: dict[str, Any] | None = None


class AcpConnection:
    """A newline-delimited JSON-RPC 2.0 connection to an ACP agent subprocess.

    Usage:
        conn = AcpConnection.spawn(["opencode", "acp"])  # or any ACP agent
        conn.on_notification("session/update", handle_update)
        conn.start()
        conn.request("initialize", {...})
        ...
        conn.close()
    """

    def __init__(self, process: subprocess.Popen) -> None:
        self._proc = process
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, _Pending] = {}
        self._pending_lock = threading.Lock()
        self._request_handlers: dict[str, RequestHandler] = {}
        self._notification_handlers: dict[str, NotificationHandler] = {}
        self._reader: threading.Thread | None = None
        self._closed = False

    # -- construction -------------------------------------------------------
    @classmethod
    def spawn(cls, command: list[str], *, cwd: str | None = None,
              env: dict[str, str] | None = None) -> "AcpConnection":
        if not command:
            raise ValueError("AcpConnection.spawn requires a non-empty command.")
        launch = _resolve_launch(command)
        proc = subprocess.Popen(
            launch,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,  # line-buffered
        )
        return cls(proc)

    # -- handler registration ----------------------------------------------
    def on_request(self, method: str, handler: RequestHandler) -> None:
        self._request_handlers[method] = handler

    def on_notification(self, method: str, handler: NotificationHandler) -> None:
        self._notification_handlers[method] = handler

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._reader is not None:
            return
        self._reader = threading.Thread(target=self._read_loop, name="acp-reader", daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._closed = True
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
        except OSError:
            pass
        if self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self._proc.kill()
                except OSError:
                    pass
        # Unblock any waiters.
        with self._pending_lock:
            for pending in self._pending.values():
                pending.error = {"code": -32000, "message": "connection closed"}
                pending.event.set()
            self._pending.clear()

    def __enter__(self) -> "AcpConnection":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- JSON-RPC core ------------------------------------------------------
    def _allocate_id(self) -> int:
        with self._id_lock:
            current = self._next_id
            self._next_id += 1
            return current

    def _write_message(self, message: dict[str, Any]) -> None:
        if self._closed or self._proc.stdin is None:
            raise AcpError("connection is closed")
        # NDJSON: a single line per message, no embedded newlines (json.dumps
        # escapes any newline inside string values), terminated by one '\n'.
        line = json.dumps(message, ensure_ascii=False)
        with self._write_lock:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method: str, params: dict[str, Any] | None = None,
                *, timeout: float = 30.0) -> Any:
        request_id = self._allocate_id()
        pending = _Pending()
        with self._pending_lock:
            self._pending[request_id] = pending
        self._write_message({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        })
        if not pending.event.wait(timeout):
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise AcpError(f"timed out waiting for response to {method!r}")
        if pending.error is not None:
            raise AcpError(f"{method} failed: {pending.error}")
        return pending.result

    # -- reader loop --------------------------------------------------------
    def _read_loop(self) -> None:
        stdout = self._proc.stdout
        if stdout is None:
            return
        for line in stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                message = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            self._dispatch(message)
        # stdout closed: unblock waiters.
        if not self._closed:
            self.close()

    def _dispatch(self, message: dict[str, Any]) -> None:
        # Response to one of our requests.
        if "id" in message and ("result" in message or "error" in message):
            self._resolve(message)
            return
        # Agent-initiated request (expects a response) or notification.
        method = message.get("method")
        if not isinstance(method, str):
            return
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if "id" in message:
            self._handle_incoming_request(message["id"], method, params)
        else:
            handler = self._notification_handlers.get(method)
            if handler is not None:
                try:
                    handler(params)
                except Exception:  # pragma: no cover - handler isolation
                    pass

    def _resolve(self, message: dict[str, Any]) -> None:
        message_id = message.get("id")
        with self._pending_lock:
            pending = self._pending.pop(message_id, None) if isinstance(message_id, int) else None
        if pending is None:
            return
        if "error" in message and message["error"] is not None:
            pending.error = message["error"]
        else:
            pending.result = message.get("result")
        pending.event.set()

    def _handle_incoming_request(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        handler = self._request_handlers.get(method)
        if handler is None:
            self._write_message({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            })
            return
        try:
            result = handler(params)
            self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result or {}})
        except Exception as exc:  # pragma: no cover - handler isolation
            self._write_message({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            })

    # -- ACP handshake helpers ---------------------------------------------
    def initialize(self, *, client_capabilities: dict[str, Any] | None = None,
                   timeout: float = 30.0) -> dict[str, Any]:
        """ACP `initialize`: negotiate protocol version + capabilities."""
        return self.request("initialize", {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "clientCapabilities": client_capabilities or {},
        }, timeout=timeout) or {}

    def new_session(self, *, cwd: str, mcp_servers: list[dict[str, Any]] | None = None,
                    timeout: float = 30.0) -> str:
        """ACP `session/new`: returns the new sessionId."""
        result = self.request("session/new", {
            "cwd": cwd,
            "mcpServers": mcp_servers or [],
        }, timeout=timeout) or {}
        return str(result.get("sessionId") or "")

    def prompt(self, *, session_id: str, text: str, timeout: float = 600.0) -> dict[str, Any]:
        """ACP `session/prompt`: send a text prompt; returns the stop result.

        Streaming `session/update` notifications arrive on the reader thread and
        should be consumed via `on_notification("session/update", ...)`.
        """
        return self.request("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": text}],
        }, timeout=timeout) or {}
