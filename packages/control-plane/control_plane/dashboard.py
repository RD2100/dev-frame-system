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
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from .client_launcher import build_client_launch_plan, render_client_launch_plan_json
from .client_manifest import render_visual_client_manifest_json
from .coding_dispatch import resolve_agent_count, resolve_coding_targets
from .go_dispatch import DEFAULT_OPENCODE_AGENT, run_go_dispatch
from .t3_bridge_bundle import build_t3_bridge_bundle, render_t3_bridge_bundle_json
from .t3_adapter import (
    build_devframe_conversation_model,
    build_t3_client_shell_from_state,
    build_t3_coordinator_entry,
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
    public_session_detail,
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
            if path == "/api/t3/conversation-model":
                body = json.dumps(build_devframe_conversation_model(), indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/coordinator-entry":
                query = parse_qs(parsed_url.query)
                selected_project_id = _first_query_value(query, "projectId", "project")
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                try:
                    from .cluster_run import list_cluster_runs

                    cluster_runs = list_cluster_runs(runtime_dir)
                except Exception:  # noqa: BLE001 - read-only projection remains best effort
                    cluster_runs = []
                address, actual_port = self.server.server_address
                shell = build_t3_client_shell_from_state(
                    state,
                    base_url=f"http://{address}:{actual_port}",
                    runtime_dir=runtime_dir,
                    cluster_runs=cluster_runs,
                )
                projects = _t3_project_options(state, include_fallback_to_cwd=False)
                body = json.dumps(
                    build_t3_coordinator_entry(
                        shell,
                        projects,
                        selected_project_id=selected_project_id,
                    ),
                    separators=(",", ":"),
                    ensure_ascii=True,
                )
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/projects":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                projects = _t3_project_options(state, include_fallback_to_cwd=False)
                body = json.dumps({"projects": projects}, indent=2, ensure_ascii=True)
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
            if path.startswith("/sessions/") and path.endswith(".json"):
                session_id = path[len("/sessions/"):-len(".json")]
                if not session_id or "/" in session_id:
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", json.dumps({"error": "session_not_found"}))
                    return
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                session = public_session_detail(state.get("sessions"), session_id)
                if session is None:
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", json.dumps({"error": "session_not_found"}))
                    return
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", json.dumps(session, indent=2, ensure_ascii=True))
                return
            if path.startswith("/sessions/"):
                session_id = unquote(path[len("/sessions/"):])
                if not session_id or "/" in session_id:
                    self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "session not found\n")
                    return
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                session = public_session_detail(state.get("sessions"), session_id)
                if session is None:
                    self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "session not found\n")
                    return
                self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", _render_session_detail_html(session))
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
            if path == "/api/mcp/connections":
                if not _client_is_loopback(self.client_address[0]):
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", json.dumps({"error": "loopback_required"}, ensure_ascii=True))
                    return
                from . import mcp_consent
                body = json.dumps({"connections": mcp_consent.list_connections()}, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/cluster-targets":
                from .cluster_control import list_cluster_targets
                project_id = ""
                query = parse_qs(parsed_url.query or "")
                if query.get("project"):
                    project_id = str(query["project"][0]).strip()
                targets = list_cluster_targets(runtime_dir, project_id)
                body = json.dumps({"projectId": project_id, "targets": targets}, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/cluster-runs":
                from .cluster_run import list_cluster_runs

                runs = list_cluster_runs(runtime_dir)
                body = json.dumps({"runs": runs}, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/cluster-roster":
                query = parse_qs(parsed_url.query or "")
                project_id = str(query["project"][0]).strip() if query.get("project") else ""
                view = _customization_layered_view(
                    "cluster-roster", runtime_dir, project_id or None
                )
                # Legacy keys (current editor reads `agents`/`source`); the
                # canonical layered view lives in builtin/global/project/effective.
                view["agents"] = view["global"]
                view["source"] = "configured" if view["global"] else "default"
                body = json.dumps(view, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/skills":
                query = parse_qs(parsed_url.query or "")
                project_id = str(query["project"][0]).strip() if query.get("project") else ""
                view = _customization_layered_view(
                    "skills", runtime_dir, project_id or None
                )
                view["custom"] = view["global"]  # legacy key
                body = json.dumps(view, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/rules":
                query = parse_qs(parsed_url.query or "")
                project_id = str(query["project"][0]).strip() if query.get("project") else ""
                view = _customization_layered_view(
                    "rules", runtime_dir, project_id or None
                )
                view["custom"] = view["global"]  # legacy key
                body = json.dumps(view, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/run-defaults":
                from .run_defaults import resolve_view as _run_defaults_view

                query = parse_qs(parsed_url.query or "")
                project_id = str(query["project"][0]).strip() if query.get("project") else ""
                body = json.dumps(
                    _run_defaults_view(runtime_dir, project_id or None),
                    indent=2,
                    ensure_ascii=True,
                )
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/memory":
                from .memory_prefs import resolve_view as _memory_view

                query = parse_qs(parsed_url.query or "")
                project_id = str(query["project"][0]).strip() if query.get("project") else ""
                body = json.dumps(
                    _memory_view(runtime_dir, project_id or None),
                    indent=2,
                    ensure_ascii=True,
                )
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if path == "/api/t3/cluster-run-events":
                from .cluster_run import ClusterRunError as _ClusterRunError, cluster_run_detail

                query = parse_qs(parsed_url.query or "")
                run_id = str(query["runId"][0]).strip() if query.get("runId") else ""
                if not run_id:
                    body = json.dumps({"error": "missing_run_id"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                try:
                    detail = cluster_run_detail(runtime_dir, run_id)
                except _ClusterRunError as exc:
                    body = json.dumps({"error": "cluster_run_not_found", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", body)
                    return
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", json.dumps(detail, indent=2, ensure_ascii=True))
                return
            if path == "/api/t3/cluster-run-agent":
                from .cluster_run import (
                    ClusterRunError as _ClusterRunError,
                    cluster_run_agent_detail,
                )

                query = parse_qs(parsed_url.query or "")
                run_id = str(query["runId"][0]).strip() if query.get("runId") else ""
                agent_id = str(query["agentId"][0]).strip() if query.get("agentId") else ""
                if not run_id or not agent_id:
                    body = json.dumps({"error": "missing_run_or_agent_id"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                try:
                    detail = cluster_run_agent_detail(runtime_dir, run_id, agent_id)
                except _ClusterRunError as exc:
                    body = json.dumps({"error": "cluster_run_agent_not_found", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", body)
                    return
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", json.dumps(detail, indent=2, ensure_ascii=True))
                return
            if path == "/healthz":
                self._send_text(HTTPStatus.OK, "text/plain; charset=utf-8", "ok\n")
                return
            self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "not found\n")

        def do_HEAD(self) -> None:
            if urlparse(self.path).path == "/state.json":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                self._send_text(
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    render_visual_control_plane_state_json(state),
                    send_body=False,
                )
                return
            self.send_error(HTTPStatus.NOT_IMPLEMENTED, f"Unsupported method ({self.command!r})")

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:
            parsed_url = urlparse(self.path)
            if parsed_url.path == "/api/t3/conversation-intake":
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
                from .conversation_intake import IntakeError, record_intake

                try:
                    result = record_intake(
                        runtime_dir,
                        payload.get("threadId"),
                        payload.get("projectId"),
                        payload.get("clientRequestId"),
                        payload.get("message"),
                        environment_id=payload.get("environmentId"),
                    )
                except IntakeError as exc:
                    detail = str(exc)
                    if detail == "unknown_thread":
                        status = HTTPStatus.NOT_FOUND
                    elif detail in {"resolution_failed", "journal_corrupt"}:
                        status = HTTPStatus.INTERNAL_SERVER_ERROR
                    else:
                        status = HTTPStatus.BAD_REQUEST
                    body = json.dumps({"accepted": False, "error": detail}, indent=2, ensure_ascii=True)
                    self._send_text(status, "application/json; charset=utf-8", body)
                    return
                from .t3_adapter import invalidate_t3_shell_cache

                invalidate_t3_shell_cache(runtime_dir)
                body = json.dumps(result, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.ACCEPTED, "application/json; charset=utf-8", body)
                return
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
                        "reason": "Only queued go_run execute actions and ready rdpaper run commands can be started from the local action endpoint.",
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
                if request_id.startswith("wb-"):
                    from .obsidian_memory import (
                        PLAN_PROPOSAL_KIND,
                        ObsidianMemoryError,
                        approve_project_plan,
                    )
                    from .writeback import (
                        WritebackError,
                        load_writeback_proposal,
                        resolve_writeback_proposal,
                    )

                    try:
                        proposal = load_writeback_proposal(runtime_dir, request_id)
                        if (
                            decision == "approve"
                            and proposal is not None
                            and proposal.get("proposal_kind") == PLAN_PROPOSAL_KIND
                        ):
                            wb = approve_project_plan(
                                runtime_dir,
                                request_id,
                                confirm=True,
                                expected_thread_id=thread_id,
                            )
                        else:
                            wb = resolve_writeback_proposal(
                                runtime_dir,
                                request_id,
                                decision,
                                expected_thread_id=thread_id,
                            )
                    except (ObsidianMemoryError, WritebackError) as exc:
                        body = json.dumps({
                            "responded": False,
                            "error": "writeback_rejected",
                            "detail": str(exc),
                            "requestId": request_id,
                        }, indent=2, ensure_ascii=True)
                        self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                        return
                    result = {
                        "responded": True,
                        "decision": decision,
                        "requestId": request_id,
                        "threadId": thread_id,
                        "executed": bool(wb.get("applied")),
                        **wb,
                    }
                    self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", json.dumps(result, indent=2, ensure_ascii=True))
                    return
                if request_id.startswith("tk-"):
                    from .task_proposals import TaskProposalError, resolve_task_proposal

                    try:
                        tk = resolve_task_proposal(runtime_dir, request_id, decision)
                    except TaskProposalError as exc:
                        body = json.dumps({
                            "responded": False,
                            "error": "task_proposal_rejected",
                            "detail": str(exc),
                            "requestId": request_id,
                        }, indent=2, ensure_ascii=True)
                        self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                        return
                    result = {
                        "responded": True,
                        "decision": decision,
                        "requestId": request_id,
                        "threadId": thread_id,
                        "executed": False,
                        **tk,
                    }
                    self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", json.dumps(result, indent=2, ensure_ascii=True))
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
            if parsed_url.path == "/api/t3/writeback-propose":
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
                relative_path = str(payload.get("relativePath") or "").strip()
                contents = payload.get("contents")
                project_id = str(payload.get("projectId") or "").strip()
                thread_id = str(payload.get("threadId") or "").strip()
                if not relative_path or not isinstance(contents, str):
                    body = json.dumps({"error": "missing_or_invalid_params", "required": ["relativePath", "contents"]}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                workspace_root = _resolve_writeback_workspace_root(runtime_dir, paper_project_dirs, project_id)
                if not workspace_root:
                    body = json.dumps({"error": "unknown_project", "projectId": project_id}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", body)
                    return
                from .writeback import WritebackError, stage_writeback_proposal

                try:
                    staged = stage_writeback_proposal(
                        runtime_dir,
                        workspace_root,
                        relative_path,
                        contents,
                        thread_id=thread_id,
                        project_id=project_id,
                    )
                except WritebackError as exc:
                    body = json.dumps({"error": "writeback_rejected", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                body = json.dumps({
                    "staged": True,
                    "requestId": staged["request_id"],
                    "preview": staged["preview"],
                    "humanGate": "POST /api/t3/approval-response with this requestId and decision=approve to apply.",
                }, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.ACCEPTED, "application/json; charset=utf-8", body)
                return
            if parsed_url.path == "/api/t3/cluster-run":
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
                    body = json.dumps({
                        "error": "invalid_json_body",
                        "detail": "Request body must be a JSON object.",
                        "retry": {"allowed": False, "action": "correct_request"},
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                target_omitted = isinstance(payload, dict) and "target" not in payload
                project_value = payload.get("projectId") if isinstance(payload, dict) else None
                target_value = payload.get("target") if isinstance(payload, dict) else None
                goal_value = payload.get("goal") if isinstance(payload, dict) else None
                selection_values = {
                    key: payload.get(key) if isinstance(payload, dict) else None
                    for key in ("executor", "modelProvider", "model")
                }
                valid_project = isinstance(project_value, str) and bool(project_value.strip())
                valid_target = target_omitted or (
                    isinstance(target_value, str) and bool(target_value.strip())
                )
                valid_goal = isinstance(goal_value, str) and bool(goal_value.strip())
                valid_selection = all(
                    key not in payload
                    or (isinstance(value, str) and bool(value.strip()))
                    for key, value in selection_values.items()
                ) if isinstance(payload, dict) else False
                if not all((valid_project, valid_target, valid_goal, valid_selection)):
                    body = json.dumps({
                        "error": "missing_or_invalid_params",
                        "detail": (
                            "projectId and goal must be non-blank strings; target is optional "
                            "but must be a non-blank string when provided; executor, "
                            "modelProvider, and model are optional but must be non-blank "
                            "strings when provided."
                        ),
                        "required": ["projectId", "goal"],
                        "retry": {"allowed": False, "action": "correct_request"},
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                project_id = project_value.strip()
                target = "coordinator" if target_omitted else target_value.strip()
                goal = goal_value.strip()
                proposed_by = str(payload.get("proposedBy") or "rd-code-editor").strip()
                executor = (
                    selection_values["executor"].strip()
                    if "executor" in payload
                    else None
                )
                model_provider = (
                    selection_values["modelProvider"].strip()
                    if "modelProvider" in payload
                    else None
                )
                model = (
                    selection_values["model"].strip()
                    if "model" in payload
                    else None
                )
                from .cluster_run import ClusterRunError, start_cluster_run

                try:
                    started = start_cluster_run(
                        runtime_dir,
                        project_id,
                        target,
                        goal,
                        proposed_by=proposed_by,
                        root_delegation=target_omitted,
                        executor=executor,
                        model_provider=model_provider,
                        model=model,
                    )
                except ClusterRunError as exc:
                    body = json.dumps({
                        "error": exc.code,
                        "detail": exc.detail,
                        "retry": exc.retry,
                    }, indent=2, ensure_ascii=True)
                    self._send_text(exc.status, "application/json; charset=utf-8", body)
                    return
                except Exception:  # noqa: BLE001 - unknown failures must stay opaque at the public boundary
                    body = json.dumps({
                        "error": "cluster_run_failed",
                        "detail": "Coordinator run could not be started.",
                        "retry": {"allowed": False, "action": "inspect_status"},
                    }, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "application/json; charset=utf-8", body)
                    return
                body = json.dumps({
                    "started": True,
                    "runId": started.get("runId"),
                    "projectId": started.get("projectId"),
                    "target": started.get("target"),
                    "goal": started.get("goal"),
                    "projectPath": started.get("projectPath"),
                    "conversationKind": started.get("conversationKind"),
                    "coordinatorScope": started.get("coordinatorScope"),
                    "projectBinding": started.get("projectBinding"),
                    **({"executor": started["executor"]} if started.get("executor") else {}),
                    **(
                        {"modelProvider": started["modelProvider"]}
                        if started.get("modelProvider")
                        else {}
                    ),
                    **({"model": started["model"]} if started.get("model") else {}),
                    **({"authority": started["authority"]} if started.get("authority") else {}),
                    **({"kind": started["kind"]} if started.get("kind") else {}),
                    **({"answer": started["answer"]} if started.get("answer") else {}),
                    "note": "Coordinator run started. Progress streams into the conversation; the dashboard only monitors.",
                }, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.ACCEPTED, "application/json; charset=utf-8", body)
                return
            if parsed_url.path in (
                "/api/t3/cluster-roster",
                "/api/t3/skills",
                "/api/t3/rules",
            ):
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
                if not isinstance(payload, dict):
                    body = json.dumps({"error": "invalid_payload"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                from .scope_resolver import Scope

                category = parsed_url.path.rsplit("/", 1)[-1]

                # Scope defaults to global for backwards compatibility.
                scope_raw = str(payload.get("scope") or "global").strip().lower()
                if scope_raw not in ("global", "project"):
                    body = json.dumps(
                        {"error": "invalid_scope", "detail": "scope must be 'global' or 'project'"},
                        indent=2,
                        ensure_ascii=True,
                    )
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                scope = Scope.GLOBAL if scope_raw == "global" else Scope.PROJECT

                project_id = str(payload.get("project") or "").strip()
                if scope == Scope.PROJECT and not project_id:
                    body = json.dumps(
                        {"error": "project_required", "detail": "project scope requires a project id"},
                        indent=2,
                        ensure_ascii=True,
                    )
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                # Accept the unified `items` key, falling back to the legacy
                # per-category key. A list (possibly empty, to clear) is required;
                # anything else is an invalid payload and writes nothing.
                items = payload.get("items")
                if items is None:
                    items = payload.get(_CUSTOMIZATION_ITEM_KEYS[category])
                if not isinstance(items, list):
                    body = json.dumps(
                        {"error": "invalid_payload", "detail": "items must be a list"},
                        indent=2,
                        ensure_ascii=True,
                    )
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                from .cluster_control import ClusterControlError
                from .custom_skills import CustomSkillError
                from .rules_config import CustomRuleError

                try:
                    _customization_save_scoped(
                        category, runtime_dir, scope, project_id or None, items
                    )
                except (ClusterControlError, CustomSkillError, CustomRuleError) as exc:
                    body = json.dumps(
                        {"error": f"{category}_rejected", "detail": str(exc)},
                        indent=2,
                        ensure_ascii=True,
                    )
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                except Exception as exc:  # noqa: BLE001 - readable error, never reset
                    body = json.dumps(
                        {"error": f"{category}_failed", "detail": str(exc)},
                        indent=2,
                        ensure_ascii=True,
                    )
                    self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "application/json; charset=utf-8", body)
                    return

                view = _customization_layered_view(category, runtime_dir, project_id or None)
                if category == "cluster-roster":
                    view["agents"] = view["global"]
                    view["source"] = "configured" if view["global"] else "default"
                else:
                    view["custom"] = view["global"]
                body = json.dumps({"saved": True, **view}, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if parsed_url.path == "/api/t3/run-defaults":
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
                if not isinstance(payload, dict):
                    body = json.dumps({"error": "invalid_payload"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                from .scope_resolver import Scope
                from .run_defaults import RunDefaultsError, resolve_view as _run_defaults_view, save_at as _save_run_defaults

                scope_raw = str(payload.get("scope") or "global").strip().lower()
                if scope_raw not in ("global", "project"):
                    body = json.dumps({"error": "invalid_scope"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                scope = Scope.GLOBAL if scope_raw == "global" else Scope.PROJECT
                project_id = str(payload.get("project") or "").strip()
                if scope == Scope.PROJECT and not project_id:
                    body = json.dumps({"error": "project_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                defaults = payload.get("defaults")
                if not isinstance(defaults, dict):
                    defaults = {
                        k: payload[k]
                        for k in ("agents", "model", "methodology")
                        if k in payload
                    }
                try:
                    _save_run_defaults(runtime_dir, scope, project_id or None, defaults)
                except RunDefaultsError as exc:
                    body = json.dumps({"error": "run_defaults_rejected", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                except Exception as exc:  # noqa: BLE001 - readable error, never reset
                    body = json.dumps({"error": "run_defaults_failed", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "application/json; charset=utf-8", body)
                    return
                body = json.dumps(
                    {"saved": True, **_run_defaults_view(runtime_dir, project_id or None)},
                    indent=2,
                    ensure_ascii=True,
                )
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if parsed_url.path == "/api/t3/memory":
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
                if not isinstance(payload, dict):
                    body = json.dumps({"error": "invalid_payload"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                from .memory_prefs import (
                    MemoryPrefsError,
                    resolve_view as _memory_view,
                    save_memory,
                    save_preferences,
                )

                # The memory category has two distinct layers; `scope` selects
                # which one is written: global preferences vs project memory.
                scope_raw = str(payload.get("scope") or "global").strip().lower()
                if scope_raw not in ("global", "project"):
                    body = json.dumps({"error": "invalid_scope"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                project_id = str(payload.get("project") or "").strip()

                # Accept `items`, falling back to the layer-specific key.
                items = payload.get("items")
                if items is None:
                    items = payload.get("preferences" if scope_raw == "global" else "memory")
                if not isinstance(items, list):
                    body = json.dumps({"error": "invalid_payload", "detail": "items must be a list"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                if scope_raw == "project" and not project_id:
                    body = json.dumps({"error": "project_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                try:
                    if scope_raw == "global":
                        save_preferences(runtime_dir, items)
                    else:
                        save_memory(runtime_dir, project_id, items)
                except MemoryPrefsError as exc:
                    body = json.dumps({"error": "memory_rejected", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                except Exception as exc:  # noqa: BLE001 - readable error, never reset
                    body = json.dumps({"error": "memory_failed", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "application/json; charset=utf-8", body)
                    return
                body = json.dumps(
                    {"saved": True, **_memory_view(runtime_dir, project_id or None)},
                    indent=2,
                    ensure_ascii=True,
                )
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if parsed_url.path in ("/api/t3/cluster-run-delete", "/api/t3/cluster-run-rename"):
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
                if not isinstance(payload, dict):
                    body = json.dumps({"error": "invalid_payload"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return

                from .cluster_run import (
                    ClusterRunError as _ClusterRunError,
                    delete_cluster_run,
                    rename_cluster_run,
                )

                run_id = str(payload.get("runId") or "").strip()
                try:
                    if parsed_url.path == "/api/t3/cluster-run-delete":
                        removed = delete_cluster_run(runtime_dir, run_id)
                        result = {"deleted": removed, "runId": run_id}
                    else:
                        record = rename_cluster_run(runtime_dir, run_id, payload.get("goal"))
                        result = {
                            "renamed": True,
                            "runId": record.get("runId"),
                            "goal": record.get("goal"),
                        }
                except _ClusterRunError as exc:
                    body = json.dumps({"error": "cluster_run_rejected", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", body)
                    return
                except Exception as exc:  # noqa: BLE001 - readable error, never reset
                    body = json.dumps({"error": "cluster_run_failed", "detail": str(exc)}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "application/json; charset=utf-8", body)
                    return
                body = json.dumps({"ok": True, **result}, indent=2, ensure_ascii=True)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            if parsed_url.path == "/api/mcp/connections/decide":
                if not _client_is_loopback(self.client_address[0]):
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", json.dumps({"error": "loopback_required"}, ensure_ascii=True))
                    return
                if not _loopback_origin_allowed(self):
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", json.dumps({"error": "loopback_origin_required"}, ensure_ascii=True))
                    return
                raw_body = self._read_body()
                try:
                    payload = json.loads(raw_body) if raw_body else {}
                except json.JSONDecodeError:
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", json.dumps({"error": "invalid_json_body"}, ensure_ascii=True))
                    return
                connection_id = str(payload.get("connectionId") or "").strip()
                decision = str(payload.get("decision") or "").strip()
                from . import mcp_consent
                try:
                    conn = mcp_consent.decide(connection_id, decision, runtime_dir=runtime_dir)
                except mcp_consent.ConsentError as exc:
                    self._send_text(HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", json.dumps({"error": "consent_error", "detail": str(exc)}, ensure_ascii=True))
                    return
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", json.dumps({"decided": True, "connection": conn}, indent=2, ensure_ascii=True))
                return
            if parsed_url.path == "/mcp":
                if not _client_is_loopback(self.client_address[0]):
                    body = json.dumps({"error": "loopback_required"}, indent=2, ensure_ascii=True)
                    self._send_text(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", body)
                    return
                from .mcp_server import handle_mcp_jsonrpc, resolve_mcp_token

                configured_token = resolve_mcp_token(runtime_dir)
                if configured_token is not None:
                    query = parse_qs(parsed_url.query)
                    provided = query.get("token", [""])[0] if query.get("token") else ""
                    if not provided:
                        auth_header = str(self.headers.get("Authorization") or "")
                        if auth_header.lower().startswith("bearer "):
                            provided = auth_header[7:].strip()
                    if provided != configured_token:
                        self._send_text(
                            HTTPStatus.UNAUTHORIZED,
                            "application/json; charset=utf-8",
                            json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "unauthorized"}}, ensure_ascii=True),
                        )
                        return
                raw_body = self._read_body()
                try:
                    payload = json.loads(raw_body) if raw_body else {}
                except json.JSONDecodeError:
                    self._send_text(
                        HTTPStatus.BAD_REQUEST,
                        "application/json; charset=utf-8",
                        json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}, ensure_ascii=True),
                    )
                    return
                address, actual_port = self.server.server_address
                request_session_id = self.headers.get("MCP-Session-Id") or self.headers.get("Mcp-Session-Id")
                response, extra_headers = handle_mcp_jsonrpc(
                    payload,
                    runtime_dir=runtime_dir,
                    paper_project_dirs=paper_project_dirs,
                    base_url=f"http://{address}:{actual_port}",
                    session_id=request_session_id,
                )
                if response is None:
                    self.send_response(HTTPStatus.ACCEPTED)
                    for header_name, header_value in extra_headers.items():
                        self.send_header(header_name, header_value)
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self._send_cors_headers()
                    self.end_headers()
                    return
                wants_sse = "text/event-stream" in str(self.headers.get("Accept") or "").lower()
                if wants_sse:
                    data = ("event: message\ndata: " + json.dumps(response, ensure_ascii=True) + "\n\n").encode("utf-8")
                    content_type = "text/event-stream; charset=utf-8"
                else:
                    data = json.dumps(response, ensure_ascii=True).encode("utf-8")
                    content_type = "application/json; charset=utf-8"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                for header_name, header_value in extra_headers.items():
                    self.send_header(header_name, header_value)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(data)
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
            allowed_methods = "GET, HEAD, OPTIONS" if urlparse(self.path).path == "/state.json" else None
            self._send_text(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "text/plain; charset=utf-8",
                "default-read-only dashboard\n",
                allowed_methods=allowed_methods,
            )

        def _send_text(
            self,
            status: HTTPStatus,
            content_type: str,
            text: str,
            allowed_methods: str | None = None,
            send_body: bool = True,
        ) -> None:
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if allowed_methods:
                self.send_header("Allow", allowed_methods)
            self._send_cors_headers()
            self.end_headers()
            if send_body:
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


def _render_session_detail_html(session: dict[str, Any]) -> str:
    """Render the already-public session projection without exposing runtime data."""
    fields = [
        ("Session ID", session.get("session_id")),
        ("Status", session.get("status")),
        ("Provider", session.get("provider")),
        ("Binding", session.get("binding_id")),
        ("Agent", session.get("agent_id")),
        ("Agent Role", session.get("agent_role")),
        ("Project", session.get("project_id")),
        ("Run ID", session.get("run_id")),
        ("TaskSpec", session.get("task_spec_id")),
        ("Messages", session.get("message_count")),
        ("Tool Calls", session.get("tool_call_count")),
        ("Changed Files", ", ".join(str(value) for value in session.get("changed_files", []))),
        ("Diff Summary", session.get("diff_summary")),
        ("Gates", ", ".join(str(value) for value in session.get("gates", []))),
        ("Actions", ", ".join(str(value) for value in session.get("actions", []))),
    ]
    rows = "\n".join(
        f"<dt>{escape(label)}</dt><dd>{escape(str(value or '-'))}</dd>"
        for label, value in fields
    )
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>DevFrame Session</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:0;background:#f8fafc;color:#111827;}",
        "main{max-width:920px;margin:0 auto;padding:32px 20px;}",
        "section{background:#fff;border:1px solid #d1d5db;border-radius:8px;padding:20px;margin-top:16px;}",
        "dl{display:grid;grid-template-columns:150px minmax(0,1fr);gap:10px 16px;}",
        "dt{font-weight:700;color:#374151;}dd{margin:0;overflow-wrap:anywhere;}",
        "a{color:#14532d;text-decoration:none;}a:hover{text-decoration:underline;}",
        "</style>",
        "</head>",
        "<body><main>",
        "<p>DevFrame Local Agent Control Plane</p>",
        "<h1>Session</h1>",
        "<section><dl>",
        rows,
        "</dl></section>",
        '<p><a href="/">Dashboard</a></p>',
        "</main></body></html>",
    ])


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
    if source_type == "run":
        if status != "ready" or str(action.get("detail") or "") != "rdpaper" or not source_id:
            return None
        command_args = action.get("command_args")
        if not isinstance(command_args, list):
            return None
        paper_args = _paper_command_args(command_args)
        if paper_args is None:
            return None
        runtime_root = _runtime_root(runtime_dir)
        argv = [sys.executable, "-m", "control_plane.cli", *paper_args]
        return {
            "kind": "paper_run_command",
            "go_run_id": source_id,
            "run_id": source_id,
            "runtime_dir": str(runtime_root),
            "argv": argv,
            "command": str(action.get("command") or " ".join(_quote_command_arg(part) for part in argv)),
        }
    return None


def _paper_command_args(command_args: list[Any]) -> list[str] | None:
    if not all(isinstance(part, str) and part for part in command_args):
        return None
    args = [str(part) for part in command_args]
    if (
        args[:2] == ["pack", "validate"]
        and len(args) == 3
        and Path(args[2]).name == "ref-paper-review-pack.zip"
    ):
        return args
    if (
        len(args) == 6
        and args[0] == "run"
        and args[1] == "--pipeline"
        and Path(args[2]).name == "reference_paper_review.yaml"
        and args[3] == "--execute"
        and args[4] == "--project"
    ):
        return args
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
                "run_id": str(plan.get("run_id") or plan["go_run_id"]),
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
        "run_id": str(plan.get("run_id") or plan["go_run_id"]),
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
        "run_id": str(plan.get("run_id") or plan["go_run_id"]),
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


def _t3_project_options(
    state: dict[str, Any],
    *,
    include_fallback_to_cwd: bool = False,
) -> list[dict[str, str]]:
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
            "projectId": str(project.get("project_id") or ""),
            "projectPath": str(root),
            "workspaceRoot": str(root),
            "label": f"{str(project.get('display_name') or project.get('project_id') or root.name)} - {root}",
        })
    if options or not include_fallback_to_cwd:
        return options
    cwd = Path.cwd().resolve()
    return [{
        "projectId": cwd.name,
        "projectPath": str(cwd),
        "workspaceRoot": str(cwd),
        "label": f"{cwd.name} - {cwd}",
    }]


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


# DevFrame-owned native client (RD-Code) desktop renderer origins. The Electron
# renderer is served from a custom protocol scheme (see ElectronProtocol.ts:
# DESKTOP_PRODUCTION_SCHEME / DESKTOP_DEVELOPMENT_SCHEME + DESKTOP_HOST), so its
# Origin header is e.g. "t3code://app" rather than a loopback http origin. These
# are trusted in addition to loopback http origins; the loopback client-IP check
# (_client_is_loopback) remains the primary security boundary.
_DEVFRAME_DESKTOP_ORIGINS = frozenset({"t3code://app", "t3code-dev://app"})


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
    if origin in _DEVFRAME_DESKTOP_ORIGINS:
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


# --- Customization layer (scope-aware categories) ---------------------------
#
# The three retrofitted categories (team roster / skills / rules) share the same
# scope-aware GET (four-layer view) and POST (scoped write) contract. These
# helpers centralize the per-category wiring so the request handlers stay thin.

# Item-list key historically accepted in the POST body per category, kept for
# backwards compatibility alongside the unified ``items`` key.
_CUSTOMIZATION_ITEM_KEYS: dict[str, str] = {
    "cluster-roster": "agents",
    "skills": "skills",
    "rules": "rules",
}


def _customization_layered_view(
    category: str,
    runtime_dir: str | Path | None,
    project_id: str | None,
) -> dict[str, Any]:
    """Build the ``{builtin, global, project, effective}`` view for a category.

    ``skills`` additionally carries ``constraints`` (deny-overrides result). When
    ``project_id`` is falsy the project layer is empty and ``effective`` is the
    global-only result (today's behavior).
    """
    if category == "cluster-roster":
        from .cluster_control import resolve_roster

        resolved = resolve_roster(runtime_dir, project_id)
    elif category == "skills":
        from .custom_skills import resolve_skills

        resolved = resolve_skills(runtime_dir, project_id)
    elif category == "rules":
        from .rules_config import resolve_rules

        resolved = resolve_rules(runtime_dir, project_id)
    else:  # pragma: no cover - defensive; callers pass a known category.
        raise ValueError(f"unknown customization category: {category!r}")

    view: dict[str, Any] = {
        "version": 1,
        "projectId": project_id or "",
        "builtin": resolved.builtin,
        "global": resolved.global_,
        "project": resolved.project,
        "effective": resolved.effective,
    }
    if resolved.constraints is not None:
        view["constraints"] = resolved.constraints
    return view


def _customization_save_scoped(
    category: str,
    runtime_dir: str | Path | None,
    scope: "Scope",
    project_id: str | None,
    items: list[Any],
) -> list[dict[str, Any]]:
    """Dispatch a scoped save to the right category module."""
    if category == "cluster-roster":
        from .cluster_control import save_at

        return save_at(runtime_dir, scope, project_id, items)
    if category == "skills":
        from .custom_skills import save_at as save_skills_at

        return save_skills_at(runtime_dir, scope, project_id, items)
    if category == "rules":
        from .rules_config import save_at as save_rules_at

        return save_rules_at(runtime_dir, scope, project_id, items)
    raise ValueError(f"unknown customization category: {category!r}")


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


def _resolve_writeback_workspace_root(
    runtime_dir: str | Path | None,
    paper_project_dirs: list[str | Path],
    project_id: str,
) -> str:
    """Server-side workspace root for a project id (never trust a client path).

    Returns the project's workspace root from the current control-plane state, or
    "" if the project is unknown. Write-back targets are confined to this root.
    """
    from .t3_adapter import _workspace_root

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
    wanted = str(project_id or "").strip()
    if not wanted:
        # Require an explicit project id; never guess a default workspace root.
        return ""
    for project in state.get("projects", []):
        if isinstance(project, dict) and str(project.get("project_id") or "") == wanted:
            return _workspace_root(project)
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
    if origin in _DEVFRAME_DESKTOP_ORIGINS:
        return True
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
