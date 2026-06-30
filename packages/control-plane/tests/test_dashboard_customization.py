"""API integration tests for the scope-aware customization endpoints (task 3.8).

Drives GET/POST for /api/t3/{cluster-roster,skills,rules} over loopback,
asserting the four-layer view, scoped-write isolation, origin/loopback gating,
and invalid-payload rejection (nothing written).
"""
from __future__ import annotations

import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from control_plane.dashboard import build_dashboard_server


def _server(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    return server, thread, base_url


def _get(base_url, path):
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(base_url, path, body, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


CASES = {
    "/api/t3/cluster-roster": [{"id": "docs", "role": "docs", "label": "Docs"}],
    "/api/t3/skills": [{"id": "my-skill", "title": "My Skill"}],
    "/api/t3/rules": [{"id": "my-rule", "priority": "P2", "rule": "do a thing"}],
}


@pytest.mark.parametrize("path,items", list(CASES.items()))
def test_get_returns_four_layer_view(tmp_path, path, items):
    server, thread, base_url = _server(tmp_path)
    try:
        view = _get(base_url, path)
        assert set(view) >= {"builtin", "global", "project", "effective"}
        assert view["project"] == []  # no project query → empty project layer
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("path,items", list(CASES.items()))
def test_scoped_post_isolation(tmp_path, path, items):
    server, thread, base_url = _server(tmp_path)
    try:
        # Write to project scope.
        status, resp = _post(base_url, path, {"scope": "project", "project": "demo", "items": items})
        assert status == 200
        assert resp["saved"] is True
        # Global file is untouched: GET without project shows empty global layer.
        view = _get(base_url, path)
        assert view["global"] == []
        # Project layer is populated when queried with the project id.
        proj_view = _get(base_url, f"{path}?project=demo")
        assert len(proj_view["project"]) == 1

        # Now write to global scope; project file must remain byte-identical.
        proj_path = (tmp_path / "runtime" / "demo" / path.rsplit("/", 1)[-1])
        # map endpoint name to file
        filename = {
            "cluster-roster": "cluster-roster.json",
            "skills": "skills.json",
            "rules": "rules.json",
        }[path.rsplit("/", 1)[-1]]
        proj_file = tmp_path / "runtime" / "demo" / filename
        before = proj_file.read_bytes()
        status, _ = _post(base_url, path, {"scope": "global", "items": items})
        assert status == 200
        assert proj_file.read_bytes() == before  # project file unchanged
        # Global layer now populated.
        view = _get(base_url, path)
        assert len(view["global"]) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_post_disallowed_origin_is_forbidden(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(
                base_url,
                "/api/t3/skills",
                {"scope": "global", "items": []},
                origin="http://evil.example.com",
            )
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("expected 403 for disallowed origin")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_post_invalid_scope_writes_nothing(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/skills", {"scope": "weird", "items": []})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400 for invalid scope")
        assert not (tmp_path / "runtime" / "skills.json").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_post_project_scope_requires_project_id(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/rules", {"scope": "project", "items": []})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400 when project scope lacks a project id")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_post_invalid_payload_writes_nothing(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/cluster-roster", {"scope": "global"})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400 for invalid payload")
        assert not (tmp_path / "runtime" / "cluster-roster.json").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
