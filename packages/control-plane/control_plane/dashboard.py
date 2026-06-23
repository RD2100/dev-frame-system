"""Read-only local dashboard server for Visual Control Plane state."""
from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .visual_state import (
    ACTION_PRIORITIES,
    ACTION_SOURCE_TYPES,
    ACTION_STATUSES,
    action_filter_values,
    build_visual_control_plane_state,
    filter_action_queue,
    render_action_queue_markdown,
    render_visual_control_plane_state_html,
    render_visual_control_plane_state_json,
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
                body = render_visual_control_plane_state_html(
                    state,
                    refresh_seconds=refresh_seconds,
                    endpoint_links=True,
                    lang=lang,
                )
                self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", body)
                return
            if path == "/state.json":
                state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
                self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", render_visual_control_plane_state_json(state))
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
            if path == "/healthz":
                self._send_text(HTTPStatus.OK, "text/plain; charset=utf-8", "ok\n")
                return
            self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "not found\n")

        def do_POST(self) -> None:
            self._method_not_allowed()

        def do_PUT(self) -> None:
            self._method_not_allowed()

        def do_DELETE(self) -> None:
            self._method_not_allowed()

        def do_PATCH(self) -> None:
            self._method_not_allowed()

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _method_not_allowed(self) -> None:
            self._send_text(HTTPStatus.METHOD_NOT_ALLOWED, "text/plain; charset=utf-8", "read-only dashboard\n")

        def _send_text(self, status: HTTPStatus, content_type: str, text: str) -> None:
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return DashboardRequestHandler


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
