"""API integration tests for /api/t3/run-defaults (task 5.5)."""
from __future__ import annotations

import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from control_plane.dashboard import build_dashboard_server


def _server(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _get(base_url, path):
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(base_url, path, body, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    request = Request(f"{base_url}{path}", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_layered_get(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        view = _get(base_url, "/api/t3/run-defaults")
        assert set(view) >= {"builtin", "global", "project", "effective"}
        assert view["effective"]["agents"] == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_scoped_post_isolation(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        status, _ = _post(base_url, "/api/t3/run-defaults", {"scope": "project", "project": "demo", "defaults": {"agents": 4}})
        assert status == 200
        # global file untouched
        assert not (tmp_path / "runtime" / "run-defaults.json").exists()
        proj_view = _get(base_url, "/api/t3/run-defaults?project=demo")
        assert proj_view["effective"]["agents"] == 4
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_disallowed_origin_forbidden(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/run-defaults", {"scope": "global", "defaults": {"agents": 2}}, origin="http://evil.example.com")
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("expected 403")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_invalid_payload_rejected(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/run-defaults", {"scope": "global", "defaults": {"agents": 0}})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400")
        assert not (tmp_path / "runtime" / "run-defaults.json").exists()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_project_scope_requires_project_id(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/run-defaults", {"scope": "project", "defaults": {"agents": 2}})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
