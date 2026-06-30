"""devframe mcp CLI — review and decide AI connection authorizations (Phase 0).

A thin HTTP client over the running dashboard's loopback endpoints, so the human
can see pending AI connections and Allow / Deny / Revoke them from a terminal
(the same decisions a desktop popup would make).
"""
from __future__ import annotations

import json
import sys
import urllib.request


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def cmd_mcp_connections(*, prog: str = "devframe mcp connections") -> int:
    import argparse

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("action", choices=["list", "allow", "allow-always", "deny", "revoke"], help="action")
    parser.add_argument("--id", default=None, help="connection id (required for allow/deny/revoke)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(sys.argv[3:])

    base = _base_url(args.host, args.port)
    try:
        if args.action == "list":
            _, data = _get(f"{base}/api/mcp/connections")
            conns = data.get("connections", [])
            if args.format == "json":
                print(json.dumps(conns, indent=2, ensure_ascii=True))
            else:
                if not conns:
                    print("No AI connections recorded.")
                for c in conns:
                    print(f"  [{c.get('status')}] {c.get('connection_id')}  client={c.get('client_name')}")
            return 0

        if not args.id:
            print(f"ERROR: --id is required for '{args.action}'", file=sys.stderr)
            return 2
        decision = {"allow": "allow_once", "allow-always": "allow_always", "deny": "deny", "revoke": "revoke"}[args.action]
        status, data = _post(f"{base}/api/mcp/connections/decide", {"connectionId": args.id, "decision": decision})
        if status != 200:
            print(f"ERROR: {data}", file=sys.stderr)
            return 2
        conn = data.get("connection", {})
        if args.format == "json":
            print(json.dumps(conn, indent=2, ensure_ascii=True))
        else:
            print(f"{args.id} -> {conn.get('status')}")
        return 0
    except OSError as exc:
        print(f"ERROR: cannot reach DevFrame dashboard at {base}: {exc}", file=sys.stderr)
        print("Start it with: devframe dashboard serve --port 8765", file=sys.stderr)
        return 2
