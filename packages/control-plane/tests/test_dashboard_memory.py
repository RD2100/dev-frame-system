"""API integration tests for /api/t3/memory (task 6.5)."""
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


def test_two_layer_get(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        view = _get(base_url, "/api/t3/memory")
        assert set(view) >= {"preferences", "memory"}
        assert view["preferences"] == []
        assert view["memory"] == []
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_scoped_post_isolation(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        # Global preferences
        status, _ = _post(base_url, "/api/t3/memory", {"scope": "global", "items": [{"id": "tone", "kind": "preference", "text": "be terse"}]})
        assert status == 200
        # Project memory
        status, _ = _post(base_url, "/api/t3/memory", {"scope": "project", "project": "demo", "items": [{"id": "arch", "kind": "architecture", "text": "hexagonal"}]})
        assert status == 200

        view = _get(base_url, "/api/t3/memory?project=demo")
        assert [e["id"] for e in view["preferences"]] == ["tone"]
        assert [e["id"] for e in view["memory"]] == ["arch"]
        # Without project, project memory is empty but preferences persist.
        view2 = _get(base_url, "/api/t3/memory")
        assert [e["id"] for e in view2["preferences"]] == ["tone"]
        assert view2["memory"] == []
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_project_memory_requires_project_id(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/memory", {"scope": "project", "items": []})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_disallowed_origin_forbidden(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/memory", {"scope": "global", "items": []}, origin="http://evil.example.com")
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("expected 403")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_invalid_entry_rejected(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/memory", {"scope": "global", "items": [{"kind": "preference", "text": "x"}]})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400")
        assert not (tmp_path / "runtime" / "preferences.json").exists()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
