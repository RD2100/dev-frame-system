"""Client smoke test: drive every /api/t3 customization category over loopback (task 10.2).

Exercises GET (layered read) + scoped POST (write round-trip) for all five
categories against a live loopback dashboard, mirroring what the RD-Code editors
do, to prove the full API surface round-trips.
"""
from __future__ import annotations

import json
from threading import Thread
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


def _post(base_url, path, body):
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_all_categories_round_trip(tmp_path):
    server, thread, base_url = _server(tmp_path)
    project = "smoke-proj"
    try:
        # Layered categories: GET four-layer view, POST project scope, read back.
        layered = {
            "/api/t3/cluster-roster": [{"id": "docs", "role": "docs", "label": "Docs"}],
            "/api/t3/skills": [{"id": "sk", "title": "Sk"}],
            "/api/t3/rules": [{"id": "r1", "priority": "P2", "rule": "do x"}],
        }
        for path, items in layered.items():
            view = _get(base_url, path)
            assert {"builtin", "global", "project", "effective"} <= set(view)
            status, resp = _post(base_url, path, {"scope": "project", "project": project, "items": items})
            assert status == 200 and resp["saved"] is True
            back = _get(base_url, f"{path}?project={project}")
            assert len(back["project"]) == 1

        # Run defaults: layered GET + scoped POST.
        view = _get(base_url, "/api/t3/run-defaults")
        assert {"builtin", "global", "project", "effective"} <= set(view)
        status, resp = _post(
            base_url, "/api/t3/run-defaults", {"scope": "project", "project": project, "defaults": {"agents": 3}}
        )
        assert status == 200
        assert _get(base_url, f"/api/t3/run-defaults?project={project}")["effective"]["agents"] == 3

        # Memory: two-layer GET + both scoped POSTs.
        view = _get(base_url, "/api/t3/memory")
        assert {"preferences", "memory"} <= set(view)
        status, _ = _post(
            base_url, "/api/t3/memory", {"scope": "global", "items": [{"id": "tone", "kind": "preference", "text": "terse"}]}
        )
        assert status == 200
        status, _ = _post(
            base_url,
            "/api/t3/memory",
            {"scope": "project", "project": project, "items": [{"id": "arch", "kind": "architecture", "text": "hex"}]},
        )
        assert status == 200
        mem = _get(base_url, f"/api/t3/memory?project={project}")
        assert [e["id"] for e in mem["preferences"]] == ["tone"]
        assert [e["id"] for e in mem["memory"]] == ["arch"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
