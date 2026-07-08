"""Governed live ACP session driver (M2, slice 1).

Drives a real ACP agent (verified against `opencode acp`, OpenCode 1.17.9) over
the transport seam in `acp_client.py`, and wires DevFrame's governance onto the
agent-initiated requests:

- `session/request_permission`: a DevFrame policy decides allow vs HOLD. The
  default baseline allows normal file edits but holds high-risk operations
  (delete, deploy, push, secret/credential access, external side effects). Every
  decision is recorded — never silent.
- `fs/read_text_file` / `fs/write_text_file`: handled against disk within the
  session cwd, so the agent's reads/writes pass through this governed seam.

The session lifecycle (started, permission decisions, result) is recorded through
the M1 `TeamRuntime`, so a live ACP session becomes a real, inspectable team fact.

Honest scope: this drives and governs a session; it does NOT yet replace
go_dispatch as the default executor (that remains deferred in the receipt).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .acp_client import AcpConnection
from .backup_guard import default_runtime_dir
from .team_runtime import TeamRuntime

# Keywords that mark an operation as high-risk -> held for human approval,
# aligned with the project safety baseline / stop-lines.
HIGH_RISK_KEYWORDS = (
    "delete", "remove", "rm ", "rmdir", "drop ", "truncate",
    "deploy", "publish", "release", "push", "force",
    "secret", "credential", "password", "token", "api key", "apikey",
    "external", "production", "prod ",
)


@dataclass
class PermissionDecision:
    allowed: bool
    option_id: str
    reason: str


@dataclass
class AcpSessionResult:
    session_id: str
    stop_reason: str
    permission_decisions: list[PermissionDecision] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    held_high_risk: int = 0


def _text_blob(value: Any) -> str:
    try:
        import json
        return json.dumps(value, ensure_ascii=False).lower()
    except (TypeError, ValueError):
        return str(value).lower()


def is_high_risk(tool_call: dict[str, Any]) -> bool:
    """Heuristic risk classification over the permission request's tool call."""
    blob = _text_blob(tool_call)
    return any(keyword in blob for keyword in HIGH_RISK_KEYWORDS)


def _classify_option(option: dict[str, Any]) -> str:
    # Token-match on optionId/kind/name (ACP kinds are like allow_once /
    # reject_once) so substrings inside words (e.g. "no" in "another") do not
    # cause misclassification.
    import re
    text = f"{option.get('optionId','')} {option.get('kind','')} {option.get('name','')}".lower()
    tokens = set(re.split(r"[^a-z]+", text))
    if tokens & {"reject", "deny", "no", "cancel", "abort", "rejected", "denied"}:
        return "reject"
    if tokens & {"allow", "proceed", "yes", "accept", "approve", "approved",
                 "accepted", "once", "always", "allowed"}:
        return "allow"
    return "unknown"


def default_permission_policy(tool_call: dict[str, Any],
                              options: list[dict[str, Any]]) -> PermissionDecision:
    """DevFrame default permission baseline.

    High-risk operations are HELD (a reject option is chosen) and recorded;
    normal operations select an allow option. Pure and unit-testable.
    """
    allow_options = [o for o in options if _classify_option(o) == "allow"]
    reject_options = [o for o in options if _classify_option(o) == "reject"]
    high_risk = is_high_risk(tool_call)
    if high_risk:
        if reject_options:
            return PermissionDecision(False, str(reject_options[0].get("optionId", "")),
                                      "high-risk operation held for human approval")
        # No explicit reject option: hold by selecting nothing safe -> deny.
        return PermissionDecision(False, "", "high-risk operation held; no reject option offered")
    if allow_options:
        return PermissionDecision(True, str(allow_options[0].get("optionId", "")),
                                  "normal operation allowed by default baseline")
    # Unknown option set: be conservative and hold.
    if reject_options:
        return PermissionDecision(False, str(reject_options[0].get("optionId", "")),
                                  "no recognizable allow option; held conservatively")
    return PermissionDecision(False, "", "no recognizable options; held conservatively")


class GovernedAcpSession:
    """Drive and govern a single ACP coding session."""

    def __init__(self, command: list[str] | None = None, *,
                 runtime_dir: str | Path | None = None,
                 cwd: str | Path | None = None,
                 team: TeamRuntime | None = None) -> None:
        self.command = command or ["opencode", "acp"]
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()
        # Reuse a shared TeamRuntime when provided so all team-event writes go
        # through one lock (e.g. when driven inside go_dispatch's thread pool).
        self.team = team if team is not None else TeamRuntime(runtime_dir=self.runtime_dir)
        self._result: AcpSessionResult | None = None

    def run(self, prompt_text: str, *, run_id: str = "", agent_id: str = "acp-agent",
            init_timeout: float = 30.0, prompt_timeout: float = 600.0,
            env_overrides: dict[str, str] | None = None) -> AcpSessionResult:
        spawn_env: dict[str, str] | None = None
        if env_overrides:
            # Merge over the inherited environment so the agent keeps PATH etc.
            import os
            spawn_env = os.environ.copy()
            spawn_env.update({str(k): str(v) for k, v in env_overrides.items()})
        conn = AcpConnection.spawn(self.command, cwd=str(self.cwd), env=spawn_env)
        result = AcpSessionResult(session_id="", stop_reason="")
        self._result = result

        conn.on_notification("session/update", lambda p: result.updates.append(p))
        conn.on_request("session/request_permission",
                        lambda p: self._handle_permission(p, result, run_id, agent_id))
        conn.on_request("fs/read_text_file", self._handle_fs_read)
        conn.on_request("fs/write_text_file", self._handle_fs_write)
        conn.start()
        try:
            conn.initialize(client_capabilities={
                "fs": {"readTextFile": True, "writeTextFile": True},
            }, timeout=init_timeout)
            session_id = conn.new_session(cwd=str(self.cwd), timeout=init_timeout)
            result.session_id = session_id
            run_key = run_id or session_id or "acp-session"
            self.team.record_workflow_event(
                run_key, phase="acp-session", status="started", role=agent_id,
                summary=f"ACP session {session_id} started: {prompt_text[:80]}",
            )
            prompt_result = conn.prompt(session_id=session_id, text=prompt_text, timeout=prompt_timeout)
            result.stop_reason = str(prompt_result.get("stopReason") or "")
            # Surface the streamed activity into the read model (low-noise: one
            # summary event with the distinct update kinds seen).
            if result.updates:
                kinds = sorted({
                    str((u.get("update") or {}).get("sessionUpdate") or "")
                    for u in result.updates if isinstance(u, dict)
                } - {""})
                self.team.record_workflow_event(
                    run_key, phase="acp-stream", status="streamed", role=agent_id,
                    summary=(
                        f"ACP session {session_id} streamed {len(result.updates)} update(s)"
                        + (f"; kinds={', '.join(kinds)}" if kinds else "")
                    ),
                )
            self.team.record_workflow_event(
                run_key, phase="acp-session", status=result.stop_reason or "completed",
                role=agent_id,
                summary=(
                    f"ACP session {session_id} ended: stop={result.stop_reason}; "
                    f"held {result.held_high_risk} high-risk request(s)."
                ),
            )
        finally:
            conn.close()
        return result

    def _handle_permission(self, params: dict[str, Any], result: AcpSessionResult,
                           run_id: str, agent_id: str) -> dict[str, Any]:
        tool_call = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
        options = params.get("options") if isinstance(params.get("options"), list) else []
        decision = default_permission_policy(tool_call, options)
        result.permission_decisions.append(decision)
        run_key = run_id or result.session_id or "acp-session"
        if not decision.allowed:
            result.held_high_risk += 1
        self.team.record_workflow_event(
            run_key, phase="permission",
            status="allowed" if decision.allowed else "held",
            role=agent_id,
            summary=f"Permission {'allowed' if decision.allowed else 'HELD'}: {decision.reason}",
        )
        # ACP permission response: select an outcome. When a concrete option was
        # chosen (allow or the reject option for a hold), select it; otherwise
        # cancel so the agent does not proceed.
        if decision.option_id:
            return {"outcome": {"outcome": "selected", "optionId": decision.option_id}}
        return {"outcome": {"outcome": "cancelled"}}

    def _handle_fs_read(self, params: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(params.get("path") or ""))
        if path is None or not path.is_file():
            return {"content": ""}
        try:
            return {"content": path.read_text(encoding="utf-8", errors="replace")}
        except OSError:
            return {"content": ""}

    def _handle_fs_write(self, params: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(params.get("path") or ""))
        content = str(params.get("content") or "")
        if path is None:
            return {}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError:
            pass
        return {}

    def _safe_path(self, raw: str) -> Path | None:
        """Resolve a path and confine it to the session cwd (no escapes)."""
        if not raw:
            return None
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self.cwd)
        except (OSError, ValueError):
            return None
        return resolved
