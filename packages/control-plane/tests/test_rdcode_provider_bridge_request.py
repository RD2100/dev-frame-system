from __future__ import annotations

import json
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from control_plane.client_launcher import build_client_launch_plan
from control_plane.t3_bridge_bundle import build_t3_bridge_bundle, install_t3_bridge_bundle


def _json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _install_generated_bridge(tmp_path: Path) -> Path:
    t3_root = tmp_path / "t3code"
    (t3_root / "apps" / "web").mkdir(parents=True)
    (t3_root / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=tmp_path / "runtime"))
    install_t3_bridge_bundle(t3_root, bundle)
    return t3_root


def _run_request_probe(
    t3_root: Path,
    probe_body: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    captures: list[dict[str, object]] = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            captures.append(
                {
                    "path": self.path,
                    "raw": raw_body,
                    "json": json.loads(raw_body),
                }
            )
            response = json.dumps(
                {
                    "started": True,
                    "runId": f"capture-{len(captures)}",
                    "target": "coordinator",
                    "goal": "captured",
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    probe_path = t3_root / "request-probe.ts"
    probe_path.write_text(
        'import { startDevFrameCoordinatorGoal, type DevFrameCoordinatorGoalRequest }\n'
        '  from "./apps/web/src/devframe/devframeShellBridge.ts";\n\n'
        f"const config = {{ controlPlaneBaseUrl: {json.dumps(base_url)} }};\n"
        + probe_body,
        encoding="utf-8",
    )
    node = shutil.which("node")
    assert node is not None, "Node.js is required for the generated bridge product-path probe"
    try:
        result = subprocess.run(
            [node, str(probe_path)],
            cwd=t3_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    return captures, json.loads(result.stdout)


def _typecheck_generated_bridge(t3_root: Path) -> None:
    tsgo = shutil.which("tsgo")
    if tsgo is None:
        return
    (t3_root / "env.d.ts").write_text(
        "interface ImportMetaEnv {\n"
        "  readonly VITE_DEVFRAME_T3_SHELL_URL?: string;\n"
        "  readonly VITE_DEVFRAME_CLIENT_PLAN_URL?: string;\n"
        "  readonly VITE_DEVFRAME_CLIENT_MANIFEST_URL?: string;\n"
        "}\n"
        "interface ImportMeta { readonly env: ImportMetaEnv; }\n",
        encoding="utf-8",
    )
    (t3_root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "allowImportingTsExtensions": True,
                    "lib": ["ES2022", "DOM"],
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "noEmit": True,
                    "strict": True,
                    "target": "ES2022",
                },
                "include": [
                    "apps/web/src/devframe/devframeShellBridge.ts",
                    "request-probe.ts",
                    "env.d.ts",
                ],
            }
        ),
        encoding="utf-8",
    )
    command = [tsgo, "--project", str(t3_root / "tsconfig.json"), "--pretty", "false"]
    if Path(tsgo).suffix.lower() in {".bat", ".cmd"}:
        command = [shutil.which("cmd") or "cmd", "/d", "/c", *command]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_bridge_posts_explicit_provider_selection_unchanged(tmp_path: Path) -> None:
    t3_root = _install_generated_bridge(tmp_path)
    selected_requests = [
        {
            "projectId": "codex-project",
            "target": "coordinator",
            "goal": "Use the explicit GPT selection",
            "executor": "codex",
            "modelProvider": "openai",
            "model": "openai/gpt-5.6-codex",
        },
        {
            "projectId": "opencode-project",
            "target": "coordinator",
            "goal": "Use the explicit OpenCode selection",
            "executor": "opencode",
            "modelProvider": "local-ollama",
            "model": " qwen3-coder:30b ",
        },
    ]
    probe_body = (
        f"const requests: DevFrameCoordinatorGoalRequest[] = {json.dumps(selected_requests)};\n"
        "for (const request of requests) {\n"
        "  await startDevFrameCoordinatorGoal(config, request);\n"
        "}\n"
        'console.log(JSON.stringify({ requestCount: requests.length }));\n'
    )

    captures, output = _run_request_probe(t3_root, probe_body)

    assert output == {"requestCount": 2}
    assert [capture["path"] for capture in captures] == [
        "/api/t3/cluster-run",
        "/api/t3/cluster-run",
    ]
    assert [capture["json"] for capture in captures] == selected_requests
    assert [capture["raw"] for capture in captures] == [
        _json_bytes(request) for request in selected_requests
    ]
    _typecheck_generated_bridge(t3_root)


def test_generated_bridge_omits_unset_selection_and_rejects_blank_values(tmp_path: Path) -> None:
    t3_root = _install_generated_bridge(tmp_path)
    omitted_request = {
        "projectId": "compatible-project",
        "target": "coordinator",
        "goal": "Keep the pre-selection request shape",
    }
    invalid_requests = [
        {**omitted_request, "executor": ""},
        {**omitted_request, "modelProvider": " \t"},
        {**omitted_request, "model": "\n"},
    ]
    expected_errors = [
        "executor must not be blank when provided",
        "modelProvider must not be blank when provided",
        "model must not be blank when provided",
    ]
    probe_body = (
        f"const omitted: DevFrameCoordinatorGoalRequest = {json.dumps(omitted_request)};\n"
        "await startDevFrameCoordinatorGoal(config, omitted);\n"
        f"const invalid: DevFrameCoordinatorGoalRequest[] = {json.dumps(invalid_requests)};\n"
        "const errors: string[] = [];\n"
        "for (const request of invalid) {\n"
        "  try {\n"
        "    await startDevFrameCoordinatorGoal(config, request);\n"
        "  } catch (error) {\n"
        "    errors.push(error instanceof Error ? error.message : String(error));\n"
        "  }\n"
        "}\n"
        "console.log(JSON.stringify({ errors }));\n"
    )

    captures, output = _run_request_probe(t3_root, probe_body)

    assert output == {"errors": expected_errors}
    assert [capture["json"] for capture in captures] == [omitted_request]
    assert [capture["raw"] for capture in captures] == [_json_bytes(omitted_request)]
    _typecheck_generated_bridge(t3_root)
