import json
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

import pytest
from jsonschema.validators import validator_for

from control_plane.cli import main as devframe_cli_main
from control_plane.client_launcher import build_client_launch_plan
from control_plane.dashboard import build_dashboard_server
from control_plane.t3_bridge_bundle import (
    build_t3_bridge_bundle,
    install_t3_bridge_bundle,
    render_bridge_source,
    render_bridge_readme,
    render_catalog_source,
    render_t3_desktop_launcher_source,
    write_t3_bridge_bundle,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_schema() -> dict:
    return json.loads((REPO_ROOT / "schemas" / "t3_bridge_bundle.schema.json").read_text(encoding="utf-8"))


def validate_schema(schema: dict, data: dict) -> None:
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(data)


def test_t3_bridge_bundle_matches_public_schema(tmp_path):
    plan = build_client_launch_plan(runtime_dir=tmp_path / "runtime", port=8788)

    bundle = build_t3_bridge_bundle(plan)

    validate_schema(load_schema(), bundle)
    assert bundle["target"]["client"] == "t3code"
    assert bundle["target"]["license"] == "MIT"
    assert bundle["environment"]["VITE_DEVFRAME_REALTIME_MODE"] == "polling"
    assert bundle["environment"]["VITE_HOSTED_APP_CHANNEL"] == "nightly"
    assert "VITE_DEVFRAME_T3_SHELL_URL" not in bundle["environment"]
    assert bundle["launch"]["t3DesktopCommand"] == "pnpm dev:desktop"
    assert bundle["launch"]["t3DesktopProdCommand"].endswith("devframe.t3desktop.prod.mjs")
    assert bundle["launch"]["t3WebCommand"].endswith("devframe.t3web.mjs")
    assert any(file["path"] == "apps/web/src/devframe/devframeShellBridge.ts" for file in bundle["files"])
    assert any(file["path"] == "apps/web/src/connection/catalog.ts" and file["action"] == "patch" for file in bundle["files"])
    assert any(file["path"] == "apps/web/src/state/shell.ts" and file["action"] == "patch" for file in bundle["files"])
    assert any(file["path"] == "apps/web/src/state/threads.ts" and file["action"] == "patch" for file in bundle["files"])
    assert any(file["path"] == "devframe.t3desktop.mjs" and file["action"] == "add" and file["status"] == "ready" for file in bundle["files"])
    assert any(file["path"] == "devframe.t3desktop.prod.mjs" and file["action"] == "add" and file["status"] == "ready" for file in bundle["files"])
    assert any(file["path"] == "devframe.t3web.mjs" and file["action"] == "add" and file["status"] == "ready" for file in bundle["files"])
    assert all(file["status"] == "ready" for file in bundle["files"])
    assert bundle["integration"]["mutationPolicy"] == "read-only"
    assert bundle["acceptance"]["t3Desktop"].endswith("devframe.t3desktop.mjs")
    assert bundle["acceptance"]["t3Web"].endswith("devframe.t3web.mjs")


def test_write_t3_bridge_bundle_creates_installable_files(tmp_path):
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=tmp_path / "runtime"))

    written = write_t3_bridge_bundle(tmp_path / "bundle", bundle)

    written_paths = {path.relative_to(tmp_path / "bundle").as_posix() for path in written}
    assert "devframe.local.json" in written_paths
    assert ".env.devframe.local" in written_paths
    assert "devframe.t3web.mjs" in written_paths
    assert "devframe.t3desktop.mjs" in written_paths
    assert "apps/web/src/devframe/devframeShellBridge.ts" in written_paths
    assert "apps/web/src/connection/catalog.ts" in written_paths
    assert "apps/web/src/state/shell.ts" in written_paths
    assert "apps/web/src/state/threads.ts" in written_paths
    source = (tmp_path / "bundle" / "apps/web/src/devframe/devframeShellBridge.ts").read_text(encoding="utf-8")
    assert "fetchDevFrameT3Shell" in source
    assert "method: \"GET\"" in source
    assert "VITE_DEVFRAME_T3_SHELL_URL" in source
    assert 'export type DevFrameThreadKind =' in source
    assert 'readonly goalProjectBindingRequired: boolean;' in source
    assert 'export interface DevFrameProjectOption {' in source
    assert 'export async function fetchDevFrameConversationModel' in source
    assert 'export async function fetchDevFrameProjectOptions' in source
    assert "export interface DevFrameCoordinatorShellEntry" in source
    assert "const DEFAULT_CONVERSATION_MODEL" in source
    assert "export function buildDevFrameCoordinatorShellEntry" in source
    assert "export async function fetchDevFrameCoordinatorShellEntry" in source
    assert 'new URL("/api/t3/coordinator-entry", config.controlPlaneBaseUrl)' in source
    assert 'thread.threadKind === "global_coordinator"' in source
    assert 'thread.threadKind === "goal_conversation"' in source
    assert "projectOptions:" in source
    assert "selectedProject:" in source
    assert "projectCoordinatorThread:" in source
    assert "shellThreads:" in source
    assert "emptyStateReason:" in source
    assert "disabledReason:" in source
    assert (
        'shellThreads.find((thread) => thread.projectId === selectedProjectId && thread.threadKind === "goal_conversation") ??'
        in source
    )
    assert 'shellThreads.find((thread) => thread.threadKind === "goal_conversation") ??' not in source
    assert 'readonly threads: readonly DevFrameT3ThreadShell[];' in source
    shell_source = (tmp_path / "bundle" / "apps/web/src/state/shell.ts").read_text(encoding="utf-8")
    assert "createShellEnvironmentAtoms" in shell_source
    assert "loadDevFrameShellState" in shell_source
    assert "createEnvironmentSnapshotAtom(environmentShell.stateAtom)" in shell_source
    thread_source = (tmp_path / "bundle" / "apps/web/src/state/threads.ts").read_text(encoding="utf-8")
    assert "loadDevFrameThreadState" in thread_source
    assert "threadDetails" in thread_source
    assert "createEnvironmentThreadDetailAtoms" in thread_source
    env_source = (tmp_path / "bundle" / ".env.devframe.local").read_text(encoding="utf-8")
    assert "VITE_DEVFRAME_REALTIME_MODE=polling" in env_source
    assert "VITE_HOSTED_APP_CHANNEL=nightly" in env_source
    launcher_source = (tmp_path / "bundle" / "devframe.t3web.mjs").read_text(encoding="utf-8")
    assert '"--filter", "@t3tools/web", "dev"' in launcher_source
    assert '"VITE_DEVFRAME_T3_SHELL_URL":' not in launcher_source
    assert '"VITE_HOSTED_APP_CHANNEL": "nightly"' in launcher_source
    assert "VITE_HTTP_URL" not in launcher_source
    desktop_launcher_source = (tmp_path / "bundle" / "devframe.t3desktop.mjs").read_text(encoding="utf-8")
    assert '"dev:desktop"' in desktop_launcher_source
    assert '"VITE_DEVFRAME_T3_SHELL_URL":' not in desktop_launcher_source
    assert '"VITE_HOSTED_APP_CHANNEL": "nightly"' in desktop_launcher_source
    assert "VITE_HTTP_URL" not in desktop_launcher_source
    assert "devframe.t3desktop.prod.mjs" in written_paths
    prod_launcher_source = (tmp_path / "bundle" / "devframe.t3desktop.prod.mjs").read_text(encoding="utf-8")
    assert '"build:desktop"' in prod_launcher_source
    assert '"start:desktop"' in prod_launcher_source
    assert '"dev:desktop"' not in prod_launcher_source
    # The hosted-app channel must NOT be baked into the desktop production build;
    # it would force isHostedStaticApp() into the read-only onboarding surface.
    assert "VITE_HOSTED_APP_CHANNEL" not in prod_launcher_source
    assert "VITE_DEVFRAME_CLIENT_PLAN_URL" in prod_launcher_source
    assert 'T3CODE_DEVFRAME_DIRECT_RENDERER = "1"' in desktop_launcher_source
    assert "T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT" in desktop_launcher_source
    assert "DesktopWindow.ts" in desktop_launcher_source
    assert "devframe-direct-renderer: patched" in desktop_launcher_source
    assert "Option.match(environment.devServerUrl" in desktop_launcher_source
    assert "url.origin" not in desktop_launcher_source
    catalog_source = (tmp_path / "bundle" / "apps/web/src/connection/catalog.ts").read_text(encoding="utf-8")
    assert 'EnvironmentId.make("devframe-local")' in catalog_source
    assert "createDevFrameEnvironmentCatalogAtoms" in catalog_source


def test_install_t3_bridge_bundle_refuses_overwrite_without_force(tmp_path):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=tmp_path / "runtime"))

    install_t3_bridge_bundle(t3_root, bundle)

    with pytest.raises(FileExistsError):
        install_t3_bridge_bundle(t3_root, bundle)


def test_install_t3_bridge_bundle_force_patches_t3_shell_state(tmp_path):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web/src/state").mkdir(parents=True)
    (t3_root / "apps/web").mkdir(parents=True, exist_ok=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    shell_path = t3_root / "apps/web/src/state/shell.ts"
    shell_path.write_text("export const original = true;\n", encoding="utf-8")
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=tmp_path / "runtime"))

    with pytest.raises(FileExistsError):
        install_t3_bridge_bundle(t3_root, bundle)

    written = install_t3_bridge_bundle(t3_root, bundle, force=True)

    written_paths = {path.relative_to(t3_root).as_posix() for path in written}
    assert "apps/web/src/state/shell.ts" in written_paths
    assert "apps/web/src/state/threads.ts" in written_paths
    assert "apps/web/src/connection/catalog.ts" in written_paths
    assert "devframe.t3web.mjs" in written_paths
    assert "devframe.t3desktop.mjs" in written_paths
    patched = shell_path.read_text(encoding="utf-8")
    assert "readDevFrameShellBridgeConfig" in patched
    assert "fetchDevFrameT3Shell" in patched
    assert "export const environmentShell" in patched
    patched_threads = (t3_root / "apps/web/src/state/threads.ts").read_text(encoding="utf-8")
    assert "readDevFrameShellBridgeConfig" in patched_threads
    assert "findDevFrameThreadDetail" in patched_threads


def test_client_bridge_cli_writes_bundle(tmp_path, monkeypatch, capsys):
    output_dir = tmp_path / "bridge"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "bridge",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
        "--output",
        str(output_dir),
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame T3 Code bridge bundle" in output
    assert "wrote" in output
    assert (output_dir / "devframe.local.json").exists()
    assert (output_dir / "devframe.t3web.mjs").exists()
    assert (output_dir / "devframe.t3desktop.mjs").exists()
    assert (output_dir / "apps/web/src/devframe/devframeShellBridge.ts").exists()
    assert (output_dir / "apps/web/src/connection/catalog.ts").exists()
    assert (output_dir / "apps/web/src/state/shell.ts").exists()
    assert (output_dir / "apps/web/src/state/threads.ts").exists()


def test_dashboard_serves_t3_bridge_bundle_endpoint(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urlopen(f"http://127.0.0.1:{server.server_address[1]}/t3-bridge.json", timeout=5) as response:
            bundle = json.loads(response.read().decode("utf-8"))

        validate_schema(load_schema(), bundle)
        assert bundle["name"] == "devframe-t3code-local-bridge"
        assert bundle["environment"]["VITE_DEVFRAME_REALTIME_MODE"] == "polling"
        assert bundle["environment"]["VITE_HOSTED_APP_CHANNEL"] == "nightly"
        assert "VITE_DEVFRAME_T3_SHELL_URL" not in bundle["environment"]
        assert bundle["integration"]["strategy"] == "reuse-t3-client-runtime-shell-and-thread-detail"
        assert bundle["acceptance"]["t3Desktop"].endswith("devframe.t3desktop.mjs")
        assert bundle["acceptance"]["t3Web"].endswith("devframe.t3web.mjs")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_serves_t3_environment_descriptor(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urlopen(f"http://127.0.0.1:{server.server_address[1]}/.well-known/t3/environment", timeout=5) as response:
            descriptor = json.loads(response.read().decode("utf-8"))

        assert descriptor["environmentId"] == "devframe-local"
        assert descriptor["label"] == "DevFrame Local Agent Control Plane"
        assert descriptor["capabilities"]["repositoryIdentity"] is False
        assert descriptor["platform"]["os"] in {"darwin", "linux", "windows", "unknown"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_serves_t3_readonly_auth_session_with_loopback_cors(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/api/auth/session",
            headers={"Origin": "http://localhost:5733"},
        )
        with urlopen(request, timeout=5) as response:
            session = json.loads(response.read().decode("utf-8"))

        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5733"
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        assert session["authenticated"] is True
        assert session["auth"]["policy"] == "unsafe-no-auth"
        assert session["scopes"] == ["orchestration:read"]

        preflight = Request(
            f"{base_url}/api/auth/session",
            method="OPTIONS",
            headers={
                "Origin": "http://localhost:5733",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "b3, traceparent",
            },
        )
        with urlopen(preflight, timeout=5) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5733"
            assert "GET" in response.headers["Access-Control-Allow-Methods"]
            assert "b3" in response.headers["Access-Control-Allow-Headers"]
            assert "traceparent" in response.headers["Access-Control-Allow-Headers"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bridge_source_includes_all_seven_team_interface_types():
    source = render_bridge_source()

    assert "DevFrameTeamAgent" in source
    assert "DevFrameTeamTask" in source
    assert "DevFrameTeamMessage" in source
    assert "DevFrameTeamEvent" in source
    assert "DevFrameTeamEvidence" in source
    assert "DevFrameTeamGate" in source
    assert "DevFrameTeamConflict" in source
    assert "DevFrameTeamProjection" in source


def test_bridge_source_includes_team_projection_review_gates_and_conflict_control():
    source = render_bridge_source()

    assert "reviewGates: readonly DevFrameTeamGate[]" in source
    assert "conflictControl: readonly DevFrameTeamConflict[]" in source


def test_bridge_source_includes_per_thread_team_refs():
    source = render_bridge_source()

    assert "DevFrameThreadTeamRefs" in source
    assert "teamTaskIds: readonly string[]" in source
    assert "teamMessageIds: readonly string[]" in source
    assert "teamEvidenceIds: readonly string[]" in source
    assert "teamReviewGateIds: readonly string[]" in source
    assert "teamConflictFiles: readonly string[]" in source


def test_bridge_source_includes_fetch_envelope_function():
    source = render_bridge_source()

    assert "fetchDevFrameT3ShellEnvelope" in source
    assert "export async function fetchDevFrameT3ShellEnvelope" in source
    assert "return sortDevFrameThreadsForDisplay((await fetchDevFrameT3ShellEnvelope(config)).t3);" in source
    assert "export function readDevFrameControlPlaneConfig" in source
    assert "export async function fetchDevFrameClusterTargets" in source
    assert "export async function startDevFrameCoordinatorGoal" in source
    assert "export function sortDevFrameThreadsForDisplay" in source
    assert "export function buildDevFrameCoordinatorShellEntry" in source
    assert "export async function fetchDevFrameCoordinatorShellEntry" in source


def test_bridge_source_envelope_includes_devframe_team():
    source = render_bridge_source()

    assert "readonly devframe:" in source
    assert "readonly team: DevFrameTeamProjection" in source


def test_bridge_source_thread_details_uses_typed_detail():
    source = render_bridge_source()

    assert "readonly threadDetails?: readonly DevFrameThreadDetail[]" in source
    assert "DevFrameThreadDetail" in source
    assert "Record<string, unknown>" in source


def test_bridge_readme_includes_team_contract_docs():
    bundle = build_t3_bridge_bundle()
    readme = render_bridge_readme(bundle)

    assert "DevFrame Team Contract" in readme
    assert "agentRegistry" in readme
    assert "taskBoard" in readme
    assert "messageBus" in readme
    assert "eventLog" in readme
    assert "evidenceStore" in readme
    assert "reviewGates" in readme
    assert "conflictControl" in readme
    assert "DevFrameThreadTeamRefs" in readme
    assert "fetchDevFrameT3ShellEnvelope" in readme
    assert "fetchDevFrameConversationModel()" in readme
    assert "fetchDevFrameProjectOptions()" in readme
    assert "readDevFrameControlPlaneConfig()" in readme
    assert "fetchDevFrameClusterTargets()" in readme
    assert "startDevFrameCoordinatorGoal()" in readme
    assert "sortDevFrameThreadsForDisplay()" in readme
    assert "fetchDevFrameCoordinatorShellEntry()" in readme


def test_catalog_source_disables_websocket_connection():
    source = render_catalog_source()

    assert "desired: false" in source
    assert "phase: \"connected\"" in source
    assert "stage: \"polling\"" in source
    assert "wsBaseUrl: devFrameWsBaseUrl()" in source


def test_catalog_source_exposes_realtime_mode_atom():
    source = render_catalog_source()

    assert "realtimeModeAtom" in source
    assert "realtimeModeValueAtom" in source
    assert '"polling"' in source


def test_catalog_source_includes_wsBaseUrl_when_not_polling():
    source = render_catalog_source({"VITE_DEVFRAME_REALTIME_MODE": "websocket"})

    assert "wsBaseUrl: devFrameWsBaseUrl()" in source


def test_catalog_source_uses_valid_connected_phase_in_polling_mode():
    source = render_catalog_source({"VITE_DEVFRAME_REALTIME_MODE": "polling"})

    assert "wsBaseUrl: devFrameWsBaseUrl()" in source
    assert "desired: false" in source
    assert "phase: \"connected\"" in source
    assert "stage: \"polling\"" in source
    assert "phase: \"disconnected\"" not in source


def test_catalog_source_devframe_connected_state_uses_valid_t3_phase():
    source = render_catalog_source()

    assert "const DEVFRAME_CONNECTED_STATE: SupervisorConnectionState = {" in source
    assert "phase: \"connected\"" in source
    assert "phase: \"disconnected\"" not in source
    assert "phase: \"offline\"" not in source
    assert "phase: \"available\"" not in source


def test_catalog_source_derives_wsBaseUrl_from_shell_url():
    source = render_catalog_source({
        "VITE_DEVFRAME_REALTIME_MODE": "polling",
        "VITE_DEVFRAME_T3_SHELL_URL": "https://example.com/t3-shell.json",
    })

    assert "wsBaseUrl: devFrameWsBaseUrl()" in source
    assert "VITE_HTTP_URL" not in source
    assert "VITE_WS_URL" not in source


def test_environment_enables_hosted_static_mode_and_excludes_native_backend_urls():
    bundle = build_t3_bridge_bundle()

    assert bundle["environment"]["VITE_HOSTED_APP_CHANNEL"] == "nightly"
    assert "VITE_HTTP_URL" not in bundle["environment"]
    assert "VITE_WS_URL" not in bundle["environment"]
    assert bundle["environment"]["VITE_DEVFRAME_REALTIME_MODE"] == "polling"
    assert "VITE_DEVFRAME_T3_SHELL_URL" not in bundle["environment"]


def test_environment_excludes_backend_urls():
    bundle = build_t3_bridge_bundle()

    assert "VITE_HTTP_URL" not in bundle["environment"]
    assert "VITE_WS_URL" not in bundle["environment"]


def test_desktop_launcher_sets_direct_renderer_env_and_patches_desktop_window():
    bundle = build_t3_bridge_bundle()
    source = render_t3_desktop_launcher_source(bundle)

    assert 'T3CODE_DEVFRAME_DIRECT_RENDERER = "1"' in source
    assert "DesktopWindow.ts" in source
    assert "devframe-direct-renderer: patched" in source
    assert "Option.match(environment.devServerUrl" in source
    assert "onSome: (url) => url.toString()" in source
    assert "onNone: () => getDesktopUrl(environment.isDevelopment)" in source
    assert "url.origin" not in source


def test_desktop_launcher_patches_remote_debugging_for_loopback_automation():
    bundle = build_t3_bridge_bundle()
    source = render_t3_desktop_launcher_source(bundle)

    assert "dev-electron.mjs" in source
    assert "devframe-remote-debugging-origin: patched" in source
    assert "devframeDebugPort = process.env.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT || remoteDebuggingPort" in source
    assert "--remote-debugging-address=127.0.0.1" in source
    assert "devServer.origin" in source
    assert "T3CODE_CDP_ALLOW_ORIGIN" in source
    assert "T3CODE_DEVFRAME_CDP_ALLOW_ORIGIN" in source
    assert "--remote-allow-origins=*" not in source
    assert "http://127.0.0.1:5173" not in source
    assert "already patched for loopback remote debugging" in source


def test_desktop_launcher_upgrades_existing_remote_debugging_patch():
    bundle = build_t3_bridge_bundle()
    source = render_t3_desktop_launcher_source(bundle)

    assert "replaceDevElectronMarkedBlock" in source
    assert "const devElectronNextLine = " in source
    assert "content.indexOf(devElectronMarker)" in source
    assert "content.indexOf(devElectronNextLine, start)" in source
    assert "Upgraded dev-electron.mjs loopback remote debugging patch." in source
    assert "Cannot upgrade remote debugging origin patch" in source


def test_desktop_launcher_source_is_valid_javascript(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for launcher syntax check")

    bundle = build_t3_bridge_bundle()
    launcher_path = tmp_path / "devframe.t3desktop.mjs"
    launcher_path.write_text(render_t3_desktop_launcher_source(bundle), encoding="utf-8")

    result = subprocess.run([node, "--check", str(launcher_path)], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr


def test_desktop_launcher_is_idempotent_when_marker_present():
    bundle = build_t3_bridge_bundle()
    source = render_t3_desktop_launcher_source(bundle)

    assert "desktopWindowContent.includes(desktopWindowMarker)" in source
    assert "already patched for direct renderer" in source


def test_desktop_launcher_fails_fast_when_upstream_line_missing_and_no_marker():
    bundle = build_t3_bridge_bundle()
    source = render_t3_desktop_launcher_source(bundle)

    assert "Cannot apply direct-renderer patch: upstream line not found in DesktopWindow.ts and no marker present" in source
    assert "process.exit(1)" in source


def test_thread_state_includes_respond_to_thread_approval_bridge():
    from control_plane.t3_bridge_bundle import render_thread_state_source

    source = render_thread_state_source()

    assert "respondToApproval: devFrameRespondToApproval" in source
    assert "devFrameRespondToApproval" in source
    assert source.index("const devFrameRespondToApproval") < source.index("export const threadEnvironment")
    assert "api/t3/approval-response" in source
    assert "readDevFrameShellBridgeConfig" in source
    assert "label: " in source and "devframe:thread:respond-to-approval" in source
    assert "run: (_registry" in source or "run(_registry" in source
    assert "AsyncResult.success" in source
    assert "value.input.requestId" in source
    assert "value.input.threadId" in source
    assert "value.input.decision" in source
    assert 'threadId: ""' not in source
    assert "execute:" not in source
    assert "Effect.tryPromise" not in source.split("const devFrameRespondToApproval")[1]
    assert "approved" not in source or '"approve"' in source


def test_shell_state_uses_swr_with_revalidate_on_mount_and_refresh():
    from control_plane.t3_bridge_bundle import render_shell_state_source

    source = render_shell_state_source()

    assert "AsyncResult.fromEffect" not in source
    assert "load: () =>" not in source
    assert "Atom.swr(" in source
    assert "revalidateOnMount: true" in source
    assert "Atom.withRefresh(" in source
    assert "loadDevFrameShellState" in source
    assert "Atom.make(loadDevFrameShellState())" in source


def test_thread_state_uses_swr_with_revalidate_on_mount_and_refresh():
    from control_plane.t3_bridge_bundle import render_thread_state_source

    source = render_thread_state_source()

    assert "AsyncResult.fromEffect" not in source
    assert "load: () =>" not in source
    assert "Atom.swr(" in source
    assert "revalidateOnMount: true" in source
    assert "Atom.withRefresh(" in source
    assert "loadDevFrameThreadState" in source
    assert "Atom.make(loadDevFrameThreadState(ref.threadId))" in source
