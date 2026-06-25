"""Default-read-only local dashboard server for Visual Control Plane state."""
from __future__ import annotations

import ipaddress
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from .client_launcher import build_client_launch_plan, render_client_launch_plan_json
from .client_manifest import render_visual_client_manifest_json
from .coding_dispatch import resolve_agent_count, resolve_coding_targets
from .go_dispatch import DEFAULT_OPENCODE_AGENT, run_go_dispatch
from .t3_bridge_bundle import build_t3_bridge_bundle, render_t3_bridge_bundle_json
from .t3_adapter import (
    build_t3_client_shell,
    render_cached_t3_client_shell_compact_json,
    render_t3_client_shell_compact_json,
    render_t3_environment_descriptor_json,
)
from .visual_state import (
    ACTION_PRIORITIES,
    ACTION_SOURCE_TYPES,
    ACTION_STATUSES,
    action_filter_values,
    build_visual_control_plane_state,
    filter_action_queue,
    public_session_summaries,
    render_action_queue_markdown,
    render_visual_control_plane_state_html,
    render_visual_control_plane_state_json,
    dashboard_t,
    resolve_dashboard_lang,
)


def build_dashboard_server(
    runtime_dir: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    refresh_seconds: int = 5,
    paper_project_dirs: list[str | Path] | None = None,
) -> ThreadingHTTPServer:
    handler = _handler_for(runtime_dir, paper_project_dirs or [], refresh_seconds)
    return ThreadingHTTPServer((host, port), handler)


def serve_dashboard(
    runtime_dir: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    refresh_seconds: int = 5,
    paper_project_dirs: list[str | Path] | None = None,
) -> None:
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        host=host,
        port=port,
        refresh_seconds=refresh_seconds,
        paper_project_dirs=paper_project_dirs,
    )
    address, actual_port = server.server_address
    print(f"DevFrame dashboard: http://{address}:{actual_port}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


def _handler_for(runtime_dir: str | Path | None, paper_project_dirs: list[str | Path],
                 refresh_seconds: int) -> type[BaseHTTPRequestHandler]:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        server_version = "DevFrameDashboard/0.1"

        def do_GET(self) -> None:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if path in {"/", "/index.html"}:
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                query = parse_qs(parsed_url.query)
                raw_lang = query.get("lang", [""])[0] if query.get("lang") else None
                lang = resolve_dashboard_lang(raw_lang)
                focus_go_run_id = _first_query_value(query, "go_run_id", "go-run-id")
                body = render_visual_control_plane_state_html(
                    state,
                    refresh_seconds=refresh_seconds,
                    endpoint_links=True,
                    lang=lang,
                    focus_go_run_id=focus_go_run_id,
                )
                self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", body)
                return
            if path == "/state.json":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", render_visual_control_plane_state_json(state))
                return
            if path == "/client-manifest.json":
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", render_visual_client_manifest_json())
                return
            if path == "/client-plan.json":
                query = parse_qs(parsed_url.query)
                lang = resolve_dashboard_lang(query.get("lang", [""])[0] if query.get("lang") else None)
                address, actual_port = self.server.server_address
                plan = build_client_launch_plan(
                    runtime_dir,
                    host=str(address),
                    port=int(actual_port),
                    lang=lang,
                    paper_project_dirs=paper_project_dirs,
                )
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", render_client_launch_plan_json(plan))
                return
            if path == "/t3-bridge.json":
                query = parse_qs(parsed_url.query)
                lang = resolve_dashboard_lang(query.get("lang", [""])[0] if query.get("lang") else None)
                address, actual_port = self.server.server_address
                plan = build_client_launch_plan(
                    runtime_dir,
                    host=str(address),
                    port=int(actual_port),
                    lang=lang,
                    paper_project_dirs=paper_project_dirs,
                )
                bundle = build_t3_bridge_bundle(plan)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", render_t3_bridge_bundle_json(bundle))
                return
            if path == "/t3-shell.json":
                address, actual_port = self.server.server_address
                body = render_cached_t3_client_shell_compact_json(
                    runtime_dir,
                    paper_project_dirs=paper_project_dirs,
                    base_url=f"http://{address}:{actual_port}",
                )
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/.well-known/t3/environment":
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", render_t3_environment_descriptor_json())
                return
            if path == "/api/auth/session":
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", _render_t3_auth_session_json())
                return
            if path == "/go/dispatch":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                query = parse_qs(parsed_url.query)
                lang = resolve_dashboard_lang(query.get("lang", [""])[0] if query.get("lang") else None)
                body = _render_go_dispatch_html(state, runtime_dir, query, lang=lang)
                self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", body)
                return
            if path == "/actions/open":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                next_actions = state.get("next_actions", [])
                query = parse_qs(parsed_url.query)
                lang = resolve_dashboard_lang(query.get("lang", [""])[0] if query.get("lang") else None)
                action_id = _first_query_value(query, "action_id", "action-id")
                if not action_id:
                    self._send_text(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", "missing action_id\n")
                    return
                action = _action_by_id(next_actions, action_id)
                if action is None:
                    self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "action not found\n")
                    return
                plan = _execution_plan_for_action(action, runtime_dir)
                body = _render_action_open_html(action, plan, lang=lang)
                self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", body)
                return
            if path == "/evidence/open":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                query = parse_qs(parsed_url.query)
                ref = _first_query_value(query, "ref")
                if not ref:
                    self._send_text(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", "missing ref\n")
                    return
                runtime_root = _runtime_root(runtime_dir)
                resolved = _resolve_evidence_ref(ref, runtime_root, state)
                if resolved is None:
                    self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "evidence not found\n")
                    return
                file_path, base = resolved
                if file_path.is_file():
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8", "failed to read evidence\n")
                        return
                    body = _render_evidence_open_html(ref, content)
                    self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", body)
                    return
                if file_path.is_dir():
                    body = _render_evidence_directory_html(ref, file_path, base)
                    self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", body)
                    return
                self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "evidence not found\n")
                return
            if path == "/review-gates/open":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                query = parse_qs(parsed_url.query)
                gate_id = _first_query_value(query, "gate_id")
                if not gate_id:
                    self._send_text(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", "missing gate_id\n")
                    return
                gate = _gate_by_id(state.get("gates", []), gate_id)
                if gate is None:
                    gate = _gate_by_id((state.get("team") or {}).get("review_gates", []), gate_id)
                if gate is None:
                    self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "gate not found\n")
                    return
                body = _render_review_gate_open_html(gate, state, runtime_dir)
                self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", body)
                return
            if path in {"/actions.json", "/actions.md"}:
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                next_actions = state.get("next_actions", [])
                query = parse_qs(parsed_url.query)
                lang = resolve_dashboard_lang(query.get("lang", [""])[0] if query.get("lang") else None)
                invalid_filters = _invalid_action_filters(query, next_actions)
                if invalid_filters:
                    body = json.dumps({
                        "error": "invalid action filter",
                        "invalid": invalid_filters,
                        "allowed": _allowed_action_filters(next_actions),
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                actions = filter_action_queue(
                    next_actions,
                    statuses=query.get("status"),
                    priorities=query.get("priority"),
                    source_types=_query_values(query, "source_type", "source-type"),
                    source_ids=_query_values(query, "source_id", "source-id"),
                    action_ids=_query_values(query, "action_id", "action-id"),
                )
                if path == "/actions.md":
                    self._send_text(
                        HTTPStatus.OK,
                        "text/markdown; charset=utf-8",
                        render_action_queue_markdown(actions, lang=lang),
                    )
                    return
                body = json.dumps({"next_actions": actions}, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/sessions.json":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                self._send_text(
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps({"sessions": public_session_summaries(state.get("sessions", []))}, indent=2, ensure_ascii=True),
                )
                return
            if path == "/web-ai-sessions.json":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                web_ai_sessions = [
                    session for session in state.get("sessions", [])
                    if isinstance(session.get("native_refs"), dict) and str(session.get("native_refs", {}).get("runtime")) == "web-ai-import"
                ]
                self._send_text(
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    json.dumps({"sessions": public_session_summaries(web_ai_sessions)}, indent=2, ensure_ascii=True),
                )
                return
            if path == "/healthz":
                self._send_text(HTTPStatus.OK, "text/plain; charset=utf-8", "ok\n")
                return
            self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "not found\n")

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:
            parsed_url = urlparse(self.path)
            if parsed_url.path == "/go/dispatch":
                if not _client_is_loopback(self.client_address[0]):
                    body = json.dumps({"error": "loopback_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", body)
                    return
                if not _post_origin_allowed(self):
                    body = json.dumps({"error": "same_origin_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", body)
                    return
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                query = _merged_post_query(parsed_url.query, self)
                try:
                    result = _run_go_dispatch_request(state, runtime_dir, query)
                except ValueError as exc:
                    if _wants_json_response(self):
                        body = json.dumps({"error": "invalid_go_dispatch_request", "detail": str(exc)}, indent=2, ensure_ascii=True)
                        self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                        return
                    lang = resolve_dashboard_lang(query.get("lang", [""])[0] if query.get("lang") else None)
                    body = _render_go_dispatch_html(state, runtime_dir, query, error=str(exc), lang=lang)
                    self._send_text(HTTPStatus.BAD_REQUEST, "text/html; charset=utf-8", body)
                    return
                if _wants_json_response(self):
                    body = json.dumps(result, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.ACCEPTED, "application/json; charset=utf-8", body)
                    return
                lang = resolve_dashboard_lang(query.get("lang", [""])[0] if query.get("lang") else None)
                location = "/" + "?" + urlencode({"lang": lang, "go_run_id": result["go_run_id"]}) + "#go-runs"
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self._send_cors_headers()
                self.end_headers()
                return
            if parsed_url.path == "/actions/execute":
                if not _client_is_loopback(self.client_address[0]):
                    body = json.dumps({"error": "loopback_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", body)
                    return
                if not _post_origin_allowed(self):
                    body = json.dumps({"error": "same_origin_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", body)
                    return
                query = _merged_post_query(parsed_url.query, self)
                action_id = _first_query_value(query, "action_id", "action-id")
                if not action_id:
                    body = json.dumps({"error": "missing_action_id"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                action = _action_by_id(state.get("next_actions", []), action_id)
                if action is None:
                    body = json.dumps({"error": "action_not_found", "action_id": action_id}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", body)
                    return
                plan = _execution_plan_for_action(action, runtime_dir)
                if plan is None:
                    body = json.dumps({
                        "error": "unsupported_action",
                        "action_id": action_id,
                        "reason": "Only queued go_run execute actions can be started from the local action endpoint.",
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.CONFLICT, "application/json; charset=utf-8", body)
                    return
                confirm = _first_query_value(query, "confirm")
                if confirm != "execute":
                    context = str(action.get("command") or plan.get("command") or "")
                    body = json.dumps({
                        "error": "human_required",
                        "action_id": action_id,
                        "confirm": "POST again with confirm=execute to start the controlled local command.",
                        "command": context,
                        "context": str(action.get("detail") or action.get("label") or ""),
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.CONFLICT, "application/json; charset=utf-8", body)
                    return
                result = _start_execution_plan(action_id, plan)
                body = json.dumps(result, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.ACCEPTED, "application/json; charset=utf-8", body)
                return
            if parsed_url.path == "/api/t3/approval-response":
                if not _client_is_loopback(self.client_address[0]):
                    body = json.dumps({"error": "loopback_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", body)
                    return
                if not _loopback_origin_allowed(self):
                    body = json.dumps({"error": "loopback_origin_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", body)
                    return
                raw_body = self._read_body()
                try:
                    payload = json.loads(raw_body) if raw_body else {}
                except json.JSONDecodeError:
                    body = json.dumps({"error": "invalid_json_body"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                request_id = str(payload.get("requestId") or "").strip()
                thread_id = str(payload.get("threadId") or "").strip()
                decision = str(payload.get("decision") or "").strip().lower()
                if not request_id or not thread_id or decision not in {"approve", "reject"}:
                    body = json.dumps({"error": "missing_or_invalid_params", "required": ["requestId", "threadId", "decision"]}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                action_id = _resolve_approval_action_id(runtime_dir, paper_project_dirs, request_id)
                if not action_id:
                    body = json.dumps({"error": "request_id_not_resolved", "requestId": request_id}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", body)
                    return
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                action = _action_by_id(state.get("next_actions", []), action_id)
                if action is None:
                    body = json.dumps({"error": "action_not_found", "requestId": request_id, "actionId": action_id}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", body)
                    return
                if decision == "reject":
                    body = json.dumps({
                        "responded": True,
                        "decision": "reject",
                        "requestId": request_id,
                        "actionId": action_id,
                        "executed": False,
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                    return
                plan = _execution_plan_for_action(action, runtime_dir)
                if plan is None:
                    body = json.dumps({
                        "responded": True,
                        "decision": "approve",
                        "requestId": request_id,
                        "actionId": action_id,
                        "executed": False,
                        "reason": "unsupported_action",
                        "actionStatus": str(action.get("status") or ""),
                        "sourceType": str(action.get("source_type") or ""),
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                    return
                result = _start_execution_plan(action_id, plan)
                result["responded"] = True
                result["decision"] = "approve"
                result["requestId"] = request_id
                body = json.dumps(result, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.ACCEPTED, "application/json; charset=utf-8", body)
                return
            self._method_not_allowed()

        def _read_body(self) -> str:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                return self.rfile.read(content_length).decode("utf-8", errors="replace")
            return ""

        def do_PUT(self) -> None:
            self._method_not_allowed()

        def do_DELETE(self) -> None:
            self._method_not_allowed()

        def do_PATCH(self) -> None:
            self._method_not_allowed()

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _method_not_allowed(self) -> None:
            self._send_text(HTTPStatus.METHOD_NOT_ALLOWED, "text/plain; charset=utf-8", "default-read-only dashboard\n")

        def _send_text(self, status: HTTPStatus, content_type: str, text: str) -> None:
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(data)

        def _send_cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if origin and _is_loopback_origin(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Credentials", "true")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "authorization, b3, baggage, content-type, dpop, traceparent, tracestate, x-b3-sampled, x-b3-spanid, x-b3-traceid",
                )
                self.send_header("Vary", "Origin")

    return DashboardRequestHandler


def _render_action_open_html(action: dict[str, Any], plan: dict[str, Any] | None, lang: str = "en") -> str:
    action_id = str(action.get("action_id") or "")
    label = str(action.get("label") or action_id)
    command = str(action.get("command") or (plan or {}).get("command") or "")
    detail = str(action.get("detail") or "")
    execute_path = _action_execute_path(action_id)
    form = ""
    if plan is not None:
        hint = "This dispatches a task intake to the @go queue and writes logs under the runtime directory." if plan.get("kind") == "session_dispatch" else "This starts a local DevFrame go-run process and writes logs under the runtime directory."
        form = (
            f'<form method="post" action="{escape(execute_path, quote=True)}">'
            '<input type="hidden" name="confirm" value="execute">'
            '<button type="submit">Start controlled execution</button>'
            "</form>"
            f'<p class="hint">{escape(hint)}</p>'
        )
    else:
        form = '<p class="hint">This action is view-only from the web endpoint. Use the command manually after clearing its gate.</p>'
    return "\n".join([
        "<!doctype html>",
        f'<html lang="{escape(dashboard_t("html_lang", lang), quote=True)}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>DevFrame Controlled Action</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f8fafc;color:#111827;}",
        "main{max-width:920px;margin:0 auto;padding:32px 20px;}",
        "section{background:#fff;border:1px solid #d1d5db;border-radius:8px;padding:20px;margin-top:16px;}",
        "dl{display:grid;grid-template-columns:150px minmax(0,1fr);gap:10px 16px;}",
        "dt{font-weight:700;color:#374151;}dd{margin:0;overflow-wrap:anywhere;}",
        "code,pre{background:#f3f4f6;border:1px solid #e5e7eb;border-radius:6px;}",
        "code{padding:2px 5px;}pre{padding:12px;overflow:auto;}",
        "button{border:0;border-radius:6px;background:#14532d;color:#fff;font-weight:700;padding:10px 14px;cursor:pointer;}",
        ".hint{color:#4b5563;}.links a{margin-right:12px;}",
        "</style>",
        "</head>",
        "<body><main>",
        "<p>DevFrame Local Agent Control Plane</p>",
        f"<h1>{escape(label)}</h1>",
        "<section>",
        "<h2>Action</h2>",
        "<dl>",
        f"<dt>Action ID</dt><dd><code>{escape(action_id)}</code></dd>",
        f"<dt>Status</dt><dd>{escape(str(action.get('status') or ''))}</dd>",
        f"<dt>Priority</dt><dd>{escape(str(action.get('priority') or ''))}</dd>",
        f"<dt>Source</dt><dd><code>{escape(str(action.get('source_type') or ''))}</code> <code>{escape(str(action.get('source_id') or ''))}</code></dd>",
        f"<dt>Detail</dt><dd>{escape(detail)}</dd>",
        "</dl>",
        "</section>",
        "<section>",
        "<h2>Command</h2>",
        f"<pre>{escape(command)}</pre>",
        form,
        "</section>",
        '<p class="links">'
        f'<a href="{escape(_action_md_path(action_id), quote=True)}">Markdown handoff</a>'
        '<a href="/actions.json">Action JSON</a>'
        '<a href="/">Dashboard</a>'
        "</p>",
        "</main></body></html>",
    ])


def _render_go_dispatch_html(
    state: dict[str, Any],
    runtime_dir: str | Path | None,
    query: dict[str, list[str]] | None = None,
    *,
    error: str = "",
    lang: str = "en",
) -> str:
    form = _go_dispatch_form_defaults(state, query or {})
    project_options = "\n".join(
        f'<option value="{escape(option["path"], quote=True)}"{_selected_attr(option["path"], form["project_path"])}>'
        f'{escape(option["label"])}'
        "</option>"
        for option in _go_dispatch_project_options(state)
    )
    targets = escape(form["targets"])
    requirement = escape(form["requirement"])
    error_block = f'<p class="hint" style="color:#991b1b;">{escape(error)}</p>' if error else ""
    changed_checked = ' checked' if form["changed"] else ""
    execute_checked = ' checked' if form["execute"] else ""
    lang_query = f"?lang={quote(lang)}" if lang else ""
    return "\n".join([
        "<!doctype html>",
        f'<html lang="{escape(dashboard_t("html_lang", lang), quote=True)}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>DevFrame /go Dispatch</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f8fafc;color:#111827;}",
        "main{max-width:960px;margin:0 auto;padding:32px 20px;}",
        "section{background:#fff;border:1px solid #d1d5db;border-radius:8px;padding:20px;margin-top:16px;}",
        "label{display:block;font-weight:700;margin-top:14px;}",
        "input,select,textarea{width:100%;margin-top:6px;border:1px solid #cbd5e1;border-radius:6px;padding:10px;font:inherit;box-sizing:border-box;}",
        "textarea{min-height:132px;resize:vertical;}",
        ".grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;}",
        ".checks{display:flex;gap:18px;flex-wrap:wrap;margin-top:16px;}",
        ".checks label{display:flex;align-items:center;gap:8px;font-weight:600;margin-top:0;}",
        ".checks input{width:auto;margin-top:0;}",
        ".actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px;}",
        "button{border:0;border-radius:6px;background:#0f172a;color:#fff;font-weight:700;padding:10px 14px;cursor:pointer;}",
        "button.secondary{background:#475569;}",
        ".hint{color:#4b5563;}",
        "pre{background:#f3f4f6;border:1px solid #e5e7eb;border-radius:6px;padding:12px;overflow:auto;}",
        "</style>",
        "</head>",
        "<body><main>",
        "<p>DevFrame Local Agent Control Plane</p>",
        "<h1>Dispatch /go coding agents</h1>",
        "<section>",
        "<p class=\"hint\">Reuse the existing /go workflow from the browser. Leave Execute immediately unchecked to prepare packets first and spend fewer worker tokens.</p>",
        error_block,
        f'<form method="post" action="/go/dispatch{lang_query}">',
        '<label for="project_path">Project</label>',
        f'<select id="project_path" name="project_path">{project_options}</select>',
        '<label for="requirement">Goal</label>',
        f'<textarea id="requirement" name="requirement" required>{requirement}</textarea>',
        '<label for="targets">Targets (one path per line, optional)</label>',
        f'<textarea id="targets" name="targets">{targets}</textarea>',
        '<div class="grid">',
        '<div><label for="agents">Agents</label>'
        f'<input id="agents" name="agents" value="{escape(form["agents"], quote=True)}"></div>',
        '<div><label for="max_agents">Max agents</label>'
        f'<input id="max_agents" name="max_agents" type="number" min="1" value="{escape(form["max_agents"], quote=True)}"></div>',
        '</div>',
        '<div class="grid">',
        '<div><label for="since">Changed since git ref</label>'
        f'<input id="since" name="since" value="{escape(form["since"], quote=True)}"></div>',
        '<div><label for="timeout">Worker timeout (seconds)</label>'
        f'<input id="timeout" name="timeout" type="number" min="1" value="{escape(form["timeout"], quote=True)}"></div>',
        '</div>',
        '<div class="checks">',
        f'<label><input type="checkbox" name="changed" value="1"{changed_checked}>Use changed git files</label>',
        f'<label><input type="checkbox" name="execute" value="1"{execute_checked}>Execute immediately</label>',
        '</div>',
        f'<input type="hidden" name="opencode_agent" value="{escape(form["opencode_agent"], quote=True)}">',
        '<div class="actions">',
        '<button type="submit">Prepare /go run</button>',
        '<a href="/" class="secondary" style="display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:6px;background:#475569;color:#fff;text-decoration:none;">Back to dashboard</a>',
        '</div>',
        "</form>",
        "</section>",
        "<section>",
        "<h2>Runtime</h2>",
        f"<pre>{escape(str(_runtime_root(runtime_dir)))}</pre>",
        "</section>",
        "</main></body></html>",
    ])


def _action_by_id(actions: object, action_id: str) -> dict[str, Any] | None:
    if not isinstance(actions, list):
        return None
    for action in actions:
        if isinstance(action, dict) and str(action.get("action_id") or "") == action_id:
            return action
    return None


def _gate_by_id(gates: object, gate_id: str) -> dict[str, Any] | None:
    if not isinstance(gates, list):
        return None
    for gate in gates:
        if isinstance(gate, dict) and str(gate.get("gate_id") or "") == gate_id:
            return gate
    return None


def _render_review_gate_open_html(
    gate: dict[str, Any],
    state: dict[str, Any],
    runtime_dir: str | Path | None,
) -> str:
    gate_id = escape(str(gate.get("gate_id") or ""))
    kind = escape(str(gate.get("kind") or ""))
    status = escape(str(gate.get("status") or ""))
    run_id = escape(str(gate.get("run_id") or ""))
    reason = escape(str(gate.get("reason") or ""))
    next_action = escape(str(gate.get("next_action") or ""))
    raw_status = str(gate.get("status") or "").strip().casefold()
    runtime_root = _runtime_root(runtime_dir)
    evidence_links = []
    evidence_refs = []
    for evidence in (state.get("team") or {}).get("evidence_store", []):
        if str(evidence.get("run_id") or "") != str(gate.get("run_id") or ""):
            continue
        ref_path = str(evidence.get("ref_path") or "")
        if not ref_path:
            continue
        try:
            safe_ref = str(Path(ref_path).relative_to(runtime_root))
        except ValueError:
            continue
        normalized_safe_ref = safe_ref.replace("\\", "/")
        if ".." in normalized_safe_ref.split("/"):
            continue
        evidence_links.append(
            f'<li><a href="{escape("/evidence/open?ref=" + quote(normalized_safe_ref, safe="/"), quote=True)}">{escape(normalized_safe_ref)}</a></li>'
        )
        evidence_refs.append(normalized_safe_ref)
    evidence_section = ""
    if evidence_links:
        evidence_section = "\n".join([
            "<section>",
            "<h2>Related Evidence</h2>",
            "<ul>",
            "\n".join(evidence_links),
            "</ul>",
            "</section>",
        ])
    repair_section = ""
    if raw_status not in {"pass", "passed", "completed", "success", "succeeded"}:
        options = _go_dispatch_project_options(state)
        selected_project = options[0]["path"] if options else str(Path.cwd().resolve())
        requirement_lines = [
            f"Repair review gate {gate.get('gate_id', '')}",
            f"Status: {gate.get('status', '')}",
            f"Kind: {gate.get('kind', '')}",
            f"Run ID: {gate.get('run_id', '')}",
            f"Reason: {gate.get('reason', '')}",
            f"Next action: {gate.get('next_action', '')}",
        ]
        if evidence_refs:
            requirement_lines.append(f"Evidence refs: {', '.join(evidence_refs)}")
        requirement = "\n".join(requirement_lines)
        project_options = "\n".join(
            f'<option value="{escape(option["path"], quote=True)}"{_selected_attr(option["path"], selected_project)}>'
            f'{escape(option["label"])}'
            "</option>"
            for option in options
        )
        repair_section = "\n".join([
            "<section>",
            "<h2>Repair Dispatch</h2>",
            '<form method="post" action="/go/dispatch">',
            '<label for="project_path">Project</label>',
            f'<select id="project_path" name="project_path">{project_options}</select>',
            '<label for="requirement">Goal</label>',
            f'<textarea id="requirement" name="requirement" required>{escape(requirement)}</textarea>',
            '<label for="targets">Targets (one path per line, optional)</label>',
            '<textarea id="targets" name="targets"></textarea>',
            '<div class="grid">',
            '<div><label for="agents">Agents</label>'
            f'<input id="agents" name="agents" value="1"></div>',
            '<div><label for="max_agents">Max agents</label>'
            f'<input id="max_agents" name="max_agents" type="number" min="1" value="1"></div>',
            '</div>',
            '<div class="grid">',
            '<div><label for="since">Changed since git ref</label>'
            '<input id="since" name="since" value=""></div>',
            '<div><label for="timeout">Worker timeout (seconds)</label>'
            '<input id="timeout" name="timeout" type="number" min="1" value="900"></div>',
            '</div>',
            '<div class="checks">',
            '<label><input type="checkbox" name="changed" value="1">Use changed git files</label>',
            '<label><input type="checkbox" name="execute" value="1">Execute immediately</label>',
            '</div>',
            f'<input type="hidden" name="opencode_agent" value="{escape(DEFAULT_OPENCODE_AGENT, quote=True)}">',
            '<div class="actions">',
            '<button type="submit">Prepare /go run</button>',
            '<a href="/" class="secondary" style="display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:6px;background:#475569;color:#fff;text-decoration:none;">Back to dashboard</a>',
            '</div>',
            "</form>",
            "</section>",
        ])
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>DevFrame Review Gate</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:0;background:#f8fafc;color:#111827;}",
        "main{max-width:920px;margin:0 auto;padding:32px 20px;}",
        "section{background:#fff;border:1px solid #d1d5db;border-radius:8px;padding:20px;margin-top:16px;}",
        "dl{display:grid;grid-template-columns:150px minmax(0,1fr);gap:10px 16px;}",
        "dt{font-weight:700;color:#374151;}dd{margin:0;overflow-wrap:anywhere;}",
        "a{color:#14532d;text-decoration:none;}",
        "a:hover{text-decoration:underline;}",
        "</style>",
        "</head>",
        "<body><main>",
        "<p>DevFrame Local Agent Control Plane</p>",
        "<h1>Review Gate</h1>",
        "<section>",
        "<h2>Gate</h2>",
        "<dl>",
        f"<dt>Gate ID</dt><dd><code>{gate_id}</code></dd>",
        f"<dt>Kind</dt><dd>{kind}</dd>",
        f"<dt>Status</dt><dd>{status}</dd>",
        f"<dt>Run ID</dt><dd><code>{run_id}</code></dd>",
        f"<dt>Reason</dt><dd>{reason or '-'}</dd>",
        f"<dt>Next Action</dt><dd>{next_action or '-'}</dd>",
        "</dl>",
        "</section>",
        evidence_section,
        repair_section,
        '<p class="links">'
        '<a href="/">Dashboard</a>'
        "</p>",
        "</main></body></html>",
    ])


def _execution_plan_for_action(action: dict[str, Any], runtime_dir: str | Path | None) -> dict[str, Any] | None:
    source_type = str(action.get("source_type") or "")
    source_id = str(action.get("source_id") or "")
    status = str(action.get("status") or "")
    action_id = str(action.get("action_id") or "")
    if source_type == "go_run":
        if status != "ready" or not action_id.endswith("-execute-action") or not source_id:
            return None
        runtime_root = _runtime_root(runtime_dir)
        argv = [
            sys.executable,
            "-m",
            "control_plane.cli",
            "code",
            "execute",
            source_id,
            "--runtime-dir",
            str(runtime_root),
        ]
        return {
            "kind": "go_run_execute",
            "go_run_id": source_id,
            "runtime_dir": str(runtime_root),
            "argv": argv,
            "command": " ".join(_quote_command_arg(part) for part in argv),
        }
    if source_type == "session":
        runtime_root = _runtime_root(runtime_dir)
        sessions_dir = runtime_root / "web-ai-sessions"
        if not sessions_dir.is_dir():
            return None
        session_file, session_data = _find_session_by_id(sessions_dir, source_id)
        if not session_file or not session_data:
            return None
        native_refs = session_data.get("native_refs")
        if not isinstance(native_refs, dict):
            return None
        if native_refs.get("outcome") != "task_intake_recorded":
            return None
        if native_refs.get("dispatch_go_run_id"):
            return None
        intake_id = str(native_refs.get("intake_id") or "")
        project_root = str(native_refs.get("project_root") or "").strip() or str(Path.cwd())
        task_title = str(native_refs.get("task_title") or intake_id)
        return {
            "kind": "session_dispatch",
            "session_id": source_id,
            "session_file": str(session_file),
            "runtime_dir": str(runtime_root),
            "project_root": project_root,
            "intake_id": intake_id,
            "command": f"dispatch-task-intakes --intake-id {intake_id} --runtime-dir {runtime_root}",
        }
    return None


def _find_session_by_id(sessions_dir: Path, session_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    for candidate in sorted(sessions_dir.glob("*.json")):
        data = _read_json_with_lock_retry(candidate)
        if isinstance(data, dict) and str(data.get("session_id") or "") == session_id:
            return candidate, data
    return None, None


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
    for attempt in range(10):
        try:
            tmp_path.replace(path)
            return
        except OSError:
            if attempt < 9:
                time.sleep(0.001 * (attempt + 1))
            else:
                raise


def _read_json_with_lock_retry(path: Path, max_attempts: int = 10) -> dict[str, Any] | None:
    for attempt in range(max_attempts):
        try:
            return json.loads(path.read_text("utf-8"))
        except PermissionError:
            if attempt < max_attempts - 1:
                time.sleep(0.001 * (attempt + 1))
            else:
                return None
        except Exception:
            return None
    return None


def _find_existing_action_run(action_runs_root: Path) -> dict[str, Any] | None:
    if not action_runs_root.exists() or not action_runs_root.is_dir():
        return None
    for entry in sorted(action_runs_root.iterdir(), reverse=True):
        if entry.is_dir():
            run_json = entry / "action-run.json"
            if run_json.exists():
                data = _read_json_with_lock_retry(run_json)
                if data is not None:
                    return data
    return None


def _start_execution_plan(action_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    if plan["kind"] == "session_dispatch":
        return _start_session_dispatch(action_id, plan)
    return _start_subprocess_execution(action_id, plan)


def _start_session_dispatch(action_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    from .web_ai_mcp_recorder import dispatch_task_intakes

    runtime_root = Path(str(plan["runtime_dir"])).resolve()
    action_runs_root = runtime_root / "action-runs" / action_id
    existing = _find_existing_action_run(action_runs_root)
    if existing is not None:
        status = str(existing.get("status") or "")
        if status in {"started", "completed"}:
            return {
                "started": False,
                "reused": True,
                "action_id": action_id,
                "action_run_id": str(existing.get("action_run_id") or ""),
                "session_id": plan.get("session_id", ""),
                "kind": plan["kind"],
                "command": plan["command"],
                "stdout_log": str(existing.get("stdout_log") or ""),
                "stderr_log": str(existing.get("stderr_log") or ""),
                "record_path": str(existing.get("record_path") or ""),
                "previous_status": status,
            }
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_dir = runtime_root / "action-runs" / action_id / stamp
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
    dispatch_result = dispatch_task_intakes(
        project_root=Path(str(plan["project_root"])).resolve(),
        runtime_dir=runtime_root,
        intake_id=plan["intake_id"],
        agents=1,
        execute=False,
    )
    dispatched = dispatch_result.get("dispatched", [])
    go_run_id = dispatched[0]["go_run_id"] if dispatched else ""
    stdout_path.write_text(json.dumps(dispatch_result, indent=2, ensure_ascii=True), encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    record_path = log_dir / "action-run.json"
    record = {
        "action_id": action_id,
        "action_run_id": stamp,
        "status": "completed" if dispatched else "failed",
        "exit_code": 0 if dispatched else 1,
        "session_id": plan["session_id"],
        "kind": plan["kind"],
        "command": plan["command"],
        "dispatched": dispatched,
        "go_run_id": go_run_id,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "record_path": str(record_path),
    }
    _atomic_json_write(record_path, record)
    return {
        "started": True,
        "reused": False,
        "action_id": action_id,
        "action_run_id": stamp,
        "kind": plan["kind"],
        "session_id": plan["session_id"],
        "dispatched": dispatched,
        "go_run_id": go_run_id,
        "command": plan["command"],
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "record_path": str(record_path),
    }


def _start_subprocess_execution(action_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    runtime_root = Path(str(plan["runtime_dir"])).resolve()
    action_runs_root = runtime_root / "action-runs" / action_id
    existing = _find_existing_action_run(action_runs_root)
    if existing is not None:
        status = str(existing.get("status") or "")
        if status in {"started", "completed"}:
            return {
                "started": False,
                "reused": True,
                "action_id": action_id,
                "action_run_id": str(existing.get("action_run_id") or ""),
                "go_run_id": plan["go_run_id"],
                "kind": plan["kind"],
                "command": plan["command"],
                "stdout_log": str(existing.get("stdout_log") or ""),
                "stderr_log": str(existing.get("stderr_log") or ""),
                "record_path": str(existing.get("record_path") or ""),
                "previous_status": status,
            }
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_dir = runtime_root / "action-runs" / action_id / stamp
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
    stdout_file = stdout_path.open("w", encoding="utf-8")
    stderr_file = stderr_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            list(plan["argv"]),
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
        )
    finally:
        stdout_file.close()
        stderr_file.close()
    record_path = log_dir / "action-run.json"
    record = {
        "action_id": action_id,
        "action_run_id": stamp,
        "status": "started",
        "pid": process.pid,
        "go_run_id": plan["go_run_id"],
        "kind": plan["kind"],
        "command": plan["command"],
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "record_path": str(record_path),
    }
    _atomic_json_write(record_path, record)

    def _update_action_run_on_exit() -> None:
        exit_code = process.wait()
        try:
            existing = json.loads(record_path.read_text("utf-8"))
        except Exception:
            existing = record
        existing["status"] = "completed" if exit_code == 0 else "failed"
        existing["exit_code"] = exit_code
        existing["completed_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_json_write(record_path, existing)

    threading.Thread(target=_update_action_run_on_exit, daemon=True).start()

    result = {
        "started": True,
        "reused": False,
        "pid": process.pid,
        "action_id": action_id,
        "action_run_id": stamp,
        "kind": plan["kind"],
        "go_run_id": plan["go_run_id"],
        "command": plan["command"],
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "record_path": str(record_path),
    }
    return result


def _runtime_root(runtime_dir: str | Path | None) -> Path:
    if runtime_dir:
        return Path(runtime_dir).resolve()
    from .backup_guard import default_runtime_dir

    return default_runtime_dir().resolve()


def _go_dispatch_project_options(state: dict[str, Any]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for project in state.get("projects", []):
        if not isinstance(project, dict):
            continue
        root = _project_root_from_contract_path(project)
        key = str(root).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        options.append({
            "project_id": str(project.get("project_id") or ""),
            "path": str(root),
            "label": f"{str(project.get('display_name') or project.get('project_id') or root.name)} - {root}",
        })
    cwd = Path.cwd().resolve()
    cwd_key = str(cwd).casefold()
    if cwd_key not in seen:
        options.append({
            "project_id": cwd.name,
            "path": str(cwd),
            "label": f"{cwd.name} - {cwd}",
        })
    return options


def _project_root_from_contract_path(project: dict[str, Any]) -> Path:
    contract_path = Path(str(project.get("contract_path") or "")).resolve()
    if contract_path.parent.name == "project-contracts":
        return contract_path.parent.parent.parent
    return contract_path.parent if str(contract_path) else Path.cwd().resolve()


def _go_dispatch_form_defaults(state: dict[str, Any], query: dict[str, list[str]]) -> dict[str, Any]:
    options = _go_dispatch_project_options(state)
    selected_project = _first_query_value(query, "project_path") or (options[0]["path"] if options else str(Path.cwd().resolve()))
    return {
        "project_path": selected_project,
        "requirement": _first_query_value(query, "requirement"),
        "targets": _first_query_value(query, "targets"),
        "agents": _first_query_value(query, "agents") or "2",
        "max_agents": _first_query_value(query, "max_agents") or "4",
        "since": _first_query_value(query, "since"),
        "timeout": _first_query_value(query, "timeout") or "900",
        "changed": _query_flag(query, "changed"),
        "execute": _query_flag(query, "execute"),
        "opencode_agent": _first_query_value(query, "opencode_agent") or DEFAULT_OPENCODE_AGENT,
    }


def _run_go_dispatch_request(
    state: dict[str, Any],
    runtime_dir: str | Path | None,
    query: dict[str, list[str]],
) -> dict[str, Any]:
    form = _go_dispatch_form_defaults(state, query)
    project_path = Path(form["project_path"]).resolve()
    allowed_paths = {option["path"].casefold() for option in _go_dispatch_project_options(state)}
    if str(project_path).casefold() not in allowed_paths:
        raise ValueError(f"project_path is not registered in this control plane: {project_path}")
    requirement = form["requirement"].strip()
    if not requirement:
        raise ValueError("requirement is required")
    targets = _parse_targets_text(form["targets"])
    targets = resolve_coding_targets(project_path, targets, changed=form["changed"], since=form["since"] or None)
    agents = resolve_agent_count(form["agents"], targets, max_agents=int(form["max_agents"]))
    timeout = int(form["timeout"])
    result = run_go_dispatch(
        project_path,
        requirement,
        runtime_dir=runtime_dir,
        agents=agents,
        targets=targets,
        execute=form["execute"],
        opencode_agent=form["opencode_agent"],
        timeout_seconds=timeout,
    )
    execute_action_id = f"{result.go_run_id}-execute-action"
    return {
        "status": result.status,
        "go_run_id": result.go_run_id,
        "project_root": result.project_root,
        "agents": len(result.agents),
        "execute": result.execute,
        "metadata_path": result.metadata_path,
        "actions_url": "/actions.json",
        "dashboard_url": f"/?go_run_id={quote(result.go_run_id)}#go-runs",
        "execute_action_url": _action_open_path(execute_action_id),
    }


def _parse_targets_text(text: str) -> list[str]:
    normalized = text.replace("\r", "\n")
    parts = [part.strip() for chunk in normalized.split("\n") for part in chunk.split(",")]
    return [part for part in parts if part]


def _query_flag(query: dict[str, list[str]], name: str) -> bool:
    value = _first_query_value(query, name)
    return value.lower() in {"1", "true", "on", "yes"}


def _selected_attr(value: str, expected: str) -> str:
    return ' selected' if value == expected else ''


def _merged_post_query(raw_query: str, handler: BaseHTTPRequestHandler) -> dict[str, list[str]]:
    query = parse_qs(raw_query)
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return query
    raw_body = handler.rfile.read(length).decode("utf-8", errors="replace")
    body_query = parse_qs(raw_body)
    for key, values in body_query.items():
        query.setdefault(key, []).extend(values)
    return query


def _first_query_value(query: dict[str, list[str]], *names: str) -> str:
    for name in names:
        values = query.get(name, [])
        if values:
            return str(values[0])
    return ""


def _client_is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _post_origin_allowed(handler: BaseHTTPRequestHandler) -> bool:
    origin = handler.headers.get("Origin")
    if not origin:
        return True
    try:
        parsed_origin = urlparse(origin)
        parsed_host = urlparse(f"http://{handler.headers.get('Host', '')}")
    except ValueError:
        return False
    if parsed_origin.scheme not in {"http", "https"}:
        return False
    origin_host = (parsed_origin.hostname or "").lower()
    request_host = (parsed_host.hostname or "").lower()
    origin_port = parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
    request_port = parsed_host.port or 80
    return bool(origin_host) and origin_host == request_host and origin_port == request_port


def _loopback_origin_allowed(handler: BaseHTTPRequestHandler) -> bool:
    origin = handler.headers.get("Origin")
    if not origin:
        return True
    try:
        parsed_origin = urlparse(origin)
    except ValueError:
        return False
    if parsed_origin.scheme not in {"http", "https"}:
        return False
    origin_host = (parsed_origin.hostname or "").lower()
    if origin_host not in {"127.0.0.1", "localhost", "::1"}:
        return False
    return True


def _resolve_approval_action_id(
    runtime_dir: str | Path | None,
    paper_project_dirs: list[str | Path],
    request_id: str,
) -> str:
    from .t3_adapter import build_t3_client_shell_from_state

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
    shell = build_t3_client_shell_from_state(state)
    for detail in shell.get("t3", {}).get("threadDetails", []):
        for activity in detail.get("activities", []):
            if activity.get("kind") == "approval.requested":
                payload = activity.get("payload") or {}
                if str(payload.get("requestId") or "") == request_id:
                    return str(payload.get("actionId") or "")
    return ""


def _action_md_path(action_id: str) -> str:
    return f"/actions.md?action_id={quote(action_id)}" if action_id else "/actions.md"


def _action_open_path(action_id: str) -> str:
    return f"/actions/open?action_id={quote(action_id)}" if action_id else "/actions/open"


def _action_execute_path(action_id: str) -> str:
    return f"/actions/execute?action_id={quote(action_id)}" if action_id else "/actions/execute"


def _quote_command_arg(value: object) -> str:
    text = str(value)
    if not text or any(ch.isspace() for ch in text) or any(ch in text for ch in ['"', "'", "&", "|"]):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _wants_json_response(handler: BaseHTTPRequestHandler) -> bool:
    accept = str(handler.headers.get("Accept") or "").lower()
    return "application/json" in accept


def _render_t3_auth_session_json() -> str:
    return json.dumps({
        "authenticated": True,
        "auth": {
            "policy": "unsafe-no-auth",
            "bootstrapMethods": [],
            "sessionMethods": ["browser-session-cookie"],
            "sessionCookieName": "devframe_t3_readonly",
        },
        "scopes": ["orchestration:read"],
        "sessionMethod": "browser-session-cookie",
        "expiresAt": "2999-12-31T23:59:59.000Z",
    }, indent=2, ensure_ascii=True)


def _is_loopback_origin(origin: str) -> bool:
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _invalid_action_filters(query: dict[str, list[str]], actions: list[dict[str, Any]]) -> dict[str, list[str]]:
    invalid: dict[str, list[str]] = {}
    status_values = query.get("status", [])
    priority_values = query.get("priority", [])
    source_type_values = _query_values(query, "source_type", "source-type")
    source_id_values = _query_values(query, "source_id", "source-id")
    action_id_values = _query_values(query, "action_id", "action-id")
    dynamic_values = action_filter_values(actions)
    _collect_invalid(invalid, "status", status_values, ACTION_STATUSES)
    _collect_invalid(invalid, "priority", priority_values, ACTION_PRIORITIES)
    _collect_invalid(invalid, "source_type", source_type_values, ACTION_SOURCE_TYPES)
    _collect_invalid(invalid, "source_id", source_id_values, tuple(dynamic_values["source_id"]))
    _collect_invalid(invalid, "action_id", action_id_values, tuple(dynamic_values["action_id"]))
    return invalid


def _query_values(query: dict[str, list[str]], *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        values.extend(query.get(name, []))
    return values


def _collect_invalid(
    invalid: dict[str, list[str]],
    key: str,
    values: list[str],
    allowed: tuple[str, ...],
) -> None:
    bad_values = [value for value in values if value not in allowed]
    if bad_values:
        invalid[key] = bad_values


def _allowed_action_filters(actions: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "status": list(ACTION_STATUSES),
        "priority": list(ACTION_PRIORITIES),
        "source_type": list(ACTION_SOURCE_TYPES),
        **action_filter_values(actions),
    }


def _resolve_evidence_ref(ref: str, runtime_root: Path, state: dict[str, Any]) -> tuple[Path, Path] | None:
    if not ref:
        return None
    normalized = ref.replace("\\", "/")
    if Path(ref).is_absolute() or normalized.startswith("/"):
        return None
    if ".." in normalized.split("/"):
        return None
    candidates = [runtime_root]
    for project in state.get("projects", []):
        if isinstance(project, dict):
            root = _project_root_from_contract_path(project)
            if root and root.exists():
                candidates.append(root)
    for base in candidates:
        candidate = (base / ref).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            continue
        if candidate.is_file() or candidate.is_dir():
            return candidate, base
    return None


def _render_evidence_open_html(ref: str, content: str) -> str:
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Evidence: {escape(ref)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:0;background:#f8fafc;color:#111827;}",
        "main{max-width:960px;margin:0 auto;padding:32px 20px;}",
        "pre{background:#f3f4f6;border:1px solid #e5e7eb;border-radius:6px;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-word;}",
        "</style>",
        "</head>",
        "<body><main>",
        f"<h1>{escape(ref)}</h1>",
        f"<pre>{escape(content)}</pre>",
        "</main></body></html>",
    ])


def _render_evidence_directory_html(ref: str, dir_path: Path, base: Path) -> str:
    children = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for child in entries:
            child_ref = str(child.relative_to(base)).replace("\\", "/")
            children.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "href": f"/evidence/open?ref={quote(child_ref)}",
            })
    except PermissionError:
        children = []
    items = "\n".join(
        f'<li><a href="{escape(item["href"], quote=True)}">{escape(item["name"])}</a>'
        + (f' <span>(dir)</span>' if item["is_dir"] else "")
        + "</li>"
        for item in children
    )
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Evidence: {escape(ref)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:0;background:#f8fafc;color:#111827;}",
        "main{max-width:960px;margin:0 auto;padding:32px 20px;}",
        "ul{list-style:none;padding:0;}",
        "li{background:#fff;border:1px solid #d1d5db;border-radius:6px;padding:10px 14px;margin-top:8px;}",
        "a{color:#14532d;text-decoration:none;}",
        "a:hover{text-decoration:underline;}",
        "</style>",
        "</head>",
        "<body><main>",
        f"<h1>Directory: {escape(ref)}</h1>",
        "<ul>",
        items,
        "</ul>",
        "</main></body></html>",
    ])
