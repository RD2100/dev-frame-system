param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$controlPlaneRoot = Join-Path $rootPath "packages\control-plane"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("devframe-wheel-smoke-" + [guid]::NewGuid().ToString("N"))
$wheelDir = Join-Path $tempRoot "wheelhouse"
$venvDir = Join-Path $tempRoot "venv"
$projectDir = Join-Path $tempRoot "demo-project"
$paperDir = Join-Path $tempRoot "paper-project"
$runtimeDir = Join-Path $tempRoot "runtime"
$goRuntimeDir = Join-Path $tempRoot "go-runtime"
$codeRuntimeDir = Join-Path $tempRoot "code-runtime"
$previewRuntimeDir = Join-Path $tempRoot "preview-runtime"

function Invoke-Step {
    param(
        [string]$Label,
        [string]$Executable,
        [string[]]$Arguments
    )

    Write-Output "[RUN] $Label"
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Remove-LocalBuildArtifacts {
    $artifactPaths = @(
        "packages\control-plane\build",
        "packages\control-plane\dist",
        "packages\control-plane\devframe_control_plane.egg-info"
    )

    foreach ($relativePath in $artifactPaths) {
        $path = Join-Path $rootPath $relativePath
        if (Test-Path -LiteralPath $path) {
            $resolved = (Resolve-Path $path).Path
            if (-not $resolved.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove outside repository: $resolved"
            }
            Remove-Item -LiteralPath $resolved -Recurse -Force
            Write-Output "[CLEAN] $relativePath"
        }
    }
}

try {
    New-Item -ItemType Directory -Path $wheelDir | Out-Null

    Invoke-Step "build control-plane wheel" "python" @(
        "-m", "pip", "wheel", $controlPlaneRoot, "-w", $wheelDir, "--no-deps"
    )

    $wheel = Get-ChildItem -LiteralPath $wheelDir -Filter "*.whl" | Select-Object -First 1
    if (-not $wheel) {
        throw "Wheel was not produced in $wheelDir"
    }

    Invoke-Step "create smoke venv" "python" @("-m", "venv", $venvDir)
    $python = Join-Path $venvDir "Scripts\python.exe"
    $devframe = Join-Path $venvDir "Scripts\devframe.exe"
    $rdgoal = Join-Path $venvDir "Scripts\rdgoal.exe"

    Invoke-Step "install wheel" $python @("-m", "pip", "install", $wheel.FullName)
    Invoke-Step "devframe help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], '--help'], text=True); assert 'DevFrame Code CLI' in text; assert 'OpenCode-first local coding tool' in text; assert 'devframe code ' in text; assert 'devframe client' in text; assert '<goal>' in text; assert 'devframe go <project> <goal>' in text; assert 'devframe dashboard serve' in text; assert 'devframe actions' in text; print('devframe help ok')",
        $devframe
    )
    Invoke-Step "devframe code help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'code', '--help'], text=True); assert 'Usage: devframe code ' in text; assert '<goal>' in text; assert '--changed' in text; assert '--agents' in text; assert '--max-agents' in text; assert '--preview' in text; assert '--worker' in text; assert '--dashboard' in text; print('devframe code help ok')",
        $devframe
    )
    Invoke-Step "devframe code execute help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'code', 'execute', '--help'], text=True); assert 'Usage: devframe code execute' in text; assert '--rerun-passed' in text; print('devframe code execute help ok')",
        $devframe
    )
    Invoke-Step "devframe code workers" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'code', 'workers'], text=True); assert 'DevFrame Code workers' in text; assert 'opencode' in text; assert 't3code' in text; assert 'codex' not in text; assert 'claude' not in text; assert 'no packets are created' in text; print('devframe code workers ok')",
        $devframe
    )
    Invoke-Step "devframe go help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'go', '--help'], text=True); assert 'Usage: devframe go <project> <goal>' in text; assert '--changed' in text; assert '--agents' in text; assert '--max-agents' in text; assert '--preview' in text; assert '--worker' in text; print('devframe go help ok')",
        $devframe
    )
    Invoke-Step "devframe run help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'run', '--help'], text=True); assert 'Usage: devframe run --pipeline <path>' in text; print('devframe run help ok')",
        $devframe
    )
    Invoke-Step "devframe dashboard help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'dashboard', '--help'], text=True); assert 'Usage: devframe dashboard serve' in text; print('devframe dashboard help ok')",
        $devframe
    )
    Invoke-Step "devframe client help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'client', '--help'], text=True); assert 'Usage: devframe client' in text; assert 'bridge' in text; assert '--dry-run' in text; assert '--open' in text; assert '--t3-root' in text; print('devframe client help ok')",
        $devframe
    )
    Invoke-Step "devframe web-ai bind-chrome help" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'web-ai', 'bind-chrome', '--help'], text=True); assert 'Usage: devframe web-ai bind-chrome' in text; assert '--cdp-endpoint' in text; assert '--dry-run' in text; print('devframe web-ai bind-chrome help ok')",
        $devframe
    )
    Invoke-Step "devframe doctor" $devframe @("doctor")
    Invoke-Step "devframe init" $devframe @("init", "code_project", $projectDir)
    Invoke-Step "devframe init paper_iteration" $devframe @("init", "paper_iteration", $paperDir)
    Invoke-Step "devframe client dry run" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'client', '--dry-run', '--runtime-dir', sys.argv[2], '--port', '8788'], text=True); assert 'DevFrame Local Agent Client' in text; assert 'Mode         : Primary T3 Code desktop/native client + DevFrame read model + /go orchestration via OpenCode workers' in text; assert 'Dashboard    : http://127.0.0.1:8788/?lang=zh-CN (auxiliary)' in text; assert 'http://127.0.0.1:8788/?lang=zh-CN' in text; assert 't3 bridge' in text; assert 't3 shell' in text; assert '/go page' in text; assert 'Write policy : read-only' in text; print('client dry run ok')",
        $devframe,
        $runtimeDir
    )
    $bridgeBundleDir = Join-Path $tempRoot "t3-bridge-bundle"
    $bridgeBundleProbe = @'
import pathlib
import subprocess
import sys

text = subprocess.check_output([
    sys.argv[1],
    'client',
    'bridge',
    '--runtime-dir',
    sys.argv[2],
    '--port',
    '8788',
    '--output',
    sys.argv[3],
], text=True)
root = pathlib.Path(sys.argv[3])
assert 'DevFrame T3 Code bridge bundle' in text
assert (root / 'devframe.local.json').exists()
env = root / '.env.devframe.local'
assert env.exists()
env_text = env.read_text(encoding='utf-8')
assert 'VITE_DEVFRAME_REALTIME_MODE=polling' in env_text
assert 'VITE_DEVFRAME_CLIENT_PLAN_URL=http://127.0.0.1:8788/client-plan.json' in env_text
assert 'VITE_DEVFRAME_CLIENT_MANIFEST_URL=http://127.0.0.1:8788/client-manifest.json' in env_text
assert 'VITE_HOSTED_APP_CHANNEL=nightly' in env_text
assert 'VITE_DEVFRAME_T3_SHELL_URL' not in env_text
assert 'VITE_HTTP_URL' not in env_text
assert 'VITE_WS_URL' not in env_text
launcher = root / 'devframe.t3web.mjs'
assert launcher.exists()
launcher_text = launcher.read_text(encoding='utf-8')
assert 'VITE_HOSTED_APP_CHANNEL' in launcher_text
assert '"VITE_DEVFRAME_T3_SHELL_URL":' not in launcher_text
assert 'VITE_HTTP_URL' not in launcher_text
assert '--filter' in launcher_text
assert '@t3tools/web' in launcher_text
assert 'dev' in launcher_text
desktop = root / 'devframe.t3desktop.mjs'
assert desktop.exists()
desktop_text = desktop.read_text(encoding='utf-8')
assert 'dev:desktop' in desktop_text
assert 'VITE_HOSTED_APP_CHANNEL' in desktop_text
assert '"VITE_DEVFRAME_T3_SHELL_URL":' not in desktop_text
assert 'VITE_HTTP_URL' not in desktop_text
source = root / 'apps/web/src/devframe/devframeShellBridge.ts'
assert source.exists()
assert 'fetchDevFrameT3Shell' in source.read_text(encoding='utf-8')
catalog = root / 'apps/web/src/connection/catalog.ts'
assert catalog.exists()
catalog_text = catalog.read_text(encoding='utf-8')
assert 'EnvironmentId.make' in catalog_text
assert 'devframe-local' in catalog_text
shell = root / 'apps/web/src/state/shell.ts'
assert shell.exists()
assert 'loadDevFrameShellState' in shell.read_text(encoding='utf-8')
threads = root / 'apps/web/src/state/threads.ts'
assert threads.exists()
thread_text = threads.read_text(encoding='utf-8')
assert 'loadDevFrameThreadState' in thread_text
assert 'threadDetails' in thread_text
print('client bridge bundle ok')
'@
    Invoke-Step "devframe client bridge bundle" $python @(
        "-c",
        $bridgeBundleProbe,
        $devframe,
        $runtimeDir,
        $bridgeBundleDir
    )
    Invoke-Step "devframe code preview" $python @(
        "-c",
        "import pathlib, subprocess, sys; text = subprocess.check_output([sys.argv[1], 'code', 'Preview worker template.', '--project', sys.argv[2], '--runtime-dir', sys.argv[3], '--agents', 'auto', '--target', 'CURRENT_STATE.yaml', '--target', 'PIPELINE.yaml', '--preview'], text=True); assert 'DevFrame coding preview' in text; assert 'agents       : 2' in text; assert 'target_bytes : ' in text; assert 'bytes=' in text; assert 'worker       : opencode model=stepfun/step-3.7-flash agent=build' in text; assert 'command: opencode run -m stepfun/step-3.7-flash --dangerously-skip-permissions --agent build' in text; assert 'You are coding shard 1/2.' in text; assert 'Prepare   : re-run without --preview to create a resumable coding run.' in text; assert not pathlib.Path(sys.argv[3]).exists(); print('code preview ok')",
        $devframe,
        $projectDir,
        $previewRuntimeDir
    )
    Invoke-Step "devframe code dry dispatch" $devframe @(
        "code", "Build an OpenCode-first programming tool MVP.",
        "--project", $projectDir,
        "--runtime-dir", $codeRuntimeDir,
        "--target", "CURRENT_STATE.yaml"
    )
    Invoke-Step "devframe code dry dispatch details" $python @(
        "-c",
        "import json, pathlib, subprocess, sys; root = pathlib.Path(sys.argv[2]); files = list((root / 'go-runs').glob('*/go-run.json')); assert len(files) == 1; data = json.loads(files[0].read_text(encoding='utf-8')); assert data['status'] == 'queued'; assert len(data['agents']) == 1; assert data['agents'][0]['targets'] == ['CURRENT_STATE.yaml']; text = subprocess.check_output([sys.argv[1], 'visual-state', '--runtime-dir', sys.argv[2]], text=True); state = json.loads(text); assert len(state['go_runs']) == 1; assert len(state['go_runs'][0]['agents']) == 1; assert len(state['runs']) == 1; print('code dispatch ok')",
        $devframe,
        $codeRuntimeDir
    )
    Invoke-Step "devframe go dry dispatch" $devframe @(
        "go", $projectDir, "Build an OpenCode-first programming tool MVP.",
        "--runtime-dir", $goRuntimeDir,
        "--agents", "2",
        "--target", "CURRENT_STATE.yaml",
        "--target", "PIPELINE.yaml"
    )
    Invoke-Step "devframe go dry dispatch details" $python @(
        "-c",
        "import json, pathlib, subprocess, sys; root = pathlib.Path(sys.argv[2]); files = list((root / 'go-runs').glob('*/go-run.json')); assert len(files) == 1; data = json.loads(files[0].read_text(encoding='utf-8')); assert data['status'] == 'queued'; assert len(data['agents']) == 2; text = subprocess.check_output([sys.argv[1], 'visual-state', '--runtime-dir', sys.argv[2]], text=True); state = json.loads(text); assert len(state['go_runs']) == 1; assert len(state['go_runs'][0]['agents']) == 2; assert len(state['runs']) == 2; assert all(run['status'] == 'pending' for run in state['runs']); assert all(run['next_command'].startswith('rdgoal worker ') for run in state['runs']); print('go dispatch ok')",
        $devframe,
        $goRuntimeDir
    )
    Invoke-Step "devframe run" $devframe @("run", "--pipeline", (Join-Path $projectDir "PIPELINE.yaml"))
    Invoke-Step "rdgoal" $rdgoal @(
        $projectDir, "Build a working MVP prototype.", "--runtime-dir", $runtimeDir, "--apply-rdinit"
    )

    $outbox = Join-Path $runtimeDir "rdgoal-outbox\demo-project"
    $packet = Get-ChildItem -LiteralPath $outbox -Directory | Select-Object -First 1
    if (-not $packet) {
        throw "rdgoal packet not produced in $outbox"
    }

    Invoke-Step "rdgoal worker" $rdgoal @("worker", $packet.FullName, "--runtime-dir", $runtimeDir)
    Invoke-Step "rdgoal digest" $rdgoal @("digest", "--runtime-dir", $runtimeDir)
    Invoke-Step "devframe visual-state" $devframe @("visual-state", "--runtime-dir", $runtimeDir)
    Invoke-Step "devframe visual-state paper project" $devframe @(
        "visual-state", "--runtime-dir", $runtimeDir, "--paper-project", $paperDir
    )
    Invoke-Step "devframe actions" $devframe @("actions", "--runtime-dir", $runtimeDir)
    Invoke-Step "devframe actions text details" $python @(
        "-c",
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], 'actions', '--runtime-dir', sys.argv[2]], text=True); assert 'id: human-gate-action' in text; assert 'devframe actions --action-id human-gate-action --format markdown' in text; print('actions text ok')",
        $devframe,
        $runtimeDir
    )
    Invoke-Step "devframe actions paper project" $devframe @(
        "actions", "--runtime-dir", $runtimeDir, "--paper-project", $paperDir, "--format", "json"
    )
    $actionsPath = Join-Path $tempRoot "actions-ready-runs.json"
    Invoke-Step "devframe actions filtered output" $devframe @(
        "actions", "--runtime-dir", $runtimeDir, "--paper-project", $paperDir,
        "--status", "ready", "--source-type", "run", "--format", "json", "--output", $actionsPath
    )
    Invoke-Step "actions filtered output details" $python @(
        "-c",
        "import json, sys; data = json.load(open(sys.argv[1], encoding='utf-8')); assert len(data['next_actions']) == 1; action = data['next_actions'][0]; assert action['source_type'] == 'run'; assert action['status'] == 'ready'; print(action['source_id'])",
        $actionsPath
    )
    Invoke-Step "devframe actions source-id filter" $devframe @(
        "actions", "--runtime-dir", $runtimeDir, "--paper-project", $paperDir,
        "--source-id", "paper-project-paper-review", "--format", "json"
    )
    $actionsMarkdownPath = Join-Path $tempRoot "ACTION_QUEUE.md"
    Invoke-Step "devframe actions markdown handoff" $devframe @(
        "actions", "--runtime-dir", $runtimeDir, "--paper-project", $paperDir,
        "--status", "ready", "--source-type", "run", "--format", "markdown", "--output", $actionsMarkdownPath
    )
    Invoke-Step "actions markdown handoff details" $python @(
        "-c",
        "import sys; text = open(sys.argv[1], encoding='utf-8').read(); assert '# Action Queue Handoff' in text; assert 'paper-project-paper-review-command-action' in text; assert 'devframe actions --action-id paper-project-paper-review-command-action --format markdown' in text; assert 'devframe run --pipeline' in text; print('markdown handoff ok')",
        $actionsMarkdownPath
    )
    Invoke-Step "visual-state run details" $python @(
        "-c",
        "from control_plane.visual_state import build_visual_control_plane_state; import sys; state = build_visual_control_plane_state(sys.argv[1]); run = state['runs'][0]; assert run['taskspec_path'].endswith('TASKSPEC.md'); assert run['next_command'].startswith('rdgoal digest --runtime-dir'); print(run['next_command'])",
        $runtimeDir
    )
    Invoke-Step "visual-state paper details" $python @(
        "-c",
        "from control_plane.visual_state import build_visual_control_plane_state; import sys; state = build_visual_control_plane_state(sys.argv[1], paper_project_dirs=[sys.argv[2]]); assert any(run['entrypoint'] == 'rdpaper' for run in state['runs']); assert any(gate['kind'] == 'privacy' for gate in state['gates']); binding = next(binding for binding in state['provider_bindings'] if binding['binding_id'] == 'paper-project-chatgpt-web'); assert binding['health'] == 'needs_login'; assert binding['adapter_config_path'].endswith('WEB_AI_ADAPTER.yaml'); assert 'Local agent writes a minimized prompt packet.' in binding['manual_fallback_instructions']; gate = next(gate for gate in state['gates'] if gate['gate_id'] == 'paper-project-chatgpt-web-safety-gate'); assert gate['status'] == 'open'; assert 'manual fallback' in gate['next_action']; assert any(action['source_id'] == gate['gate_id'] for action in state['next_actions']); print(binding['binding_id'])",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "devframe visual-state html" $devframe @(
        "visual-state", "--runtime-dir", $runtimeDir, "--format", "html", "--output", (Join-Path $tempRoot "visual-state.html")
    )
    Invoke-Step "dashboard server import" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; server = build_dashboard_server(port=0); print(server.server_address); server.server_close()"
    )
    Invoke-Step "dashboard home endpoint links" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); html = urlopen(f'http://127.0.0.1:{server.server_address[1]}/', timeout=5).read().decode('utf-8'); q = chr(34); assert '/state.json' in html; assert '/client-plan.json' in html; assert '/client-manifest.json' in html; assert '/t3-bridge.json' in html; assert '/t3-shell.json' in html; assert '/sessions.json' in html; assert '/actions.json' in html; assert '/actions.md' in html; assert '/go/dispatch' in html; assert 'Start dispatch' in html; assert 'actions.md?action_id=' in html; assert ('aria-label=' + q + 'Language' + q) in html; assert ('aria-current=' + q + 'true' + q + ' href=' + q + '?lang=en' + q) in html; assert ('href=' + q + '?lang=zh-CN' + q) in html; assert 'Gate Focus' in html; assert 'paper-project-privacy-gate' in html; assert 'paper-project-privacy-gate-action' in html; assert '/actions.md?action_id=paper-project-privacy-gate-action' in html; assert '<dt>Current Decision</dt>' in html; assert 'paper-project-paper-decision' in html; assert 'Complete the provider safety gate, then prepare the privacy-safe paper task packet.' in html; assert '<th>Provider</th>' in html; assert '<th>Binding Health</th>' in html; assert 'paper-reviewer-paper-project-chatgpt-web' in html; assert 'chatgpt' in html; assert 'needs_login' in html; assert '<th>Action ID</th>' in html; assert '<th>Resume Filter</th>' in html; assert '<th>Manual Fallback</th>' in html; assert 'Local agent writes a minimized prompt packet.' in html; assert 'paper-project-paper-review-command-action' in html; assert 'devframe actions --action-id paper-project-paper-review-command-action --format markdown' in html; print('dashboard links ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard client plan endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urlopen(f'http://127.0.0.1:{server.server_address[1]}/client-plan.json?lang=zh-CN', timeout=5).read().decode('utf-8')); assert data['name'] == 'devframe-local-agent-client'; assert data['launch']['url'].endswith('/?lang=zh-CN'); assert data['reuse']['visualClient']['candidate'] == 't3code'; assert data['reuse']['executor']['candidate'] == 'opencode'; assert data['writePolicy']['default'] == 'read-only'; assert data['endpoints']['t3Bridge'].endswith('/t3-bridge.json'); assert data['endpoints']['t3Shell'].endswith('/t3-shell.json'); assert data['endpoints']['goDispatch'].endswith('/go/dispatch'); print('client plan ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard client manifest endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urlopen(f'http://127.0.0.1:{server.server_address[1]}/client-manifest.json', timeout=5).read().decode('utf-8')); assert data['reuse']['client'] == 't3code'; assert data['reuse']['executor'] == 'opencode'; assert data['transport']['client_plan_endpoint'] == '/client-plan.json'; assert data['transport']['t3_bridge_endpoint'] == '/t3-bridge.json'; assert data['transport']['t3_environment_endpoint'] == '/.well-known/t3/environment'; assert data['transport']['t3_auth_session_endpoint'] == '/api/auth/session'; assert data['transport']['shell_endpoint'] == '/t3-shell.json'; assert data['write_policy']['default'] == 'read-only'; assert set(data['write_policy']['blocked_methods']) == {'PUT', 'PATCH', 'DELETE'}; assert any(endpoint['path'] == '/client-plan.json' for endpoint in data['endpoints']); assert any(endpoint['path'] == '/t3-bridge.json' for endpoint in data['endpoints']); assert any(endpoint['path'] == '/.well-known/t3/environment' for endpoint in data['endpoints']); assert any(endpoint['path'] == '/api/auth/session' for endpoint in data['endpoints']); assert any(endpoint['path'] == '/t3-shell.json' for endpoint in data['endpoints']); assert any(endpoint['path'] == '/sessions.json' for endpoint in data['endpoints']); assert any(endpoint['path'] == '/go/dispatch' and endpoint['method'] == 'GET' and endpoint['mutates'] is False for endpoint in data['endpoints']); assert any(endpoint['path'] == '/go/dispatch' and endpoint['method'] == 'POST' and endpoint['mutates'] is True for endpoint in data['endpoints']); assert any(endpoint['path'] == '/actions/open' and endpoint['method'] == 'GET' and endpoint['mutates'] is False for endpoint in data['endpoints']); assert any(endpoint['path'] == '/actions/execute' and endpoint['method'] == 'POST' and endpoint['mutates'] is True for endpoint in data['endpoints']); assert any(item['path'] == '/go/dispatch' for item in data['write_policy']['allowed_mutation_endpoints']); assert any(item['path'] == '/actions/execute' for item in data['write_policy']['allowed_mutation_endpoints']); assert any(mapping['id'] == 'client-launch' and mapping['status'] == 'ready' for mapping in data['surface_mappings']); assert any(mapping['id'] == 't3-bridge' and mapping['status'] == 'ready' for mapping in data['surface_mappings']); assert any(mapping['id'] == 'go-dispatch' and mapping['status'] == 'ready' for mapping in data['surface_mappings']); assert any(mapping['id'] == 'controlled-action-execution' and mapping['status'] == 'ready' for mapping in data['surface_mappings']); assert any(mapping['id'] == 'opencode-executor-events' and mapping['status'] == 'adapter-required' for mapping in data['surface_mappings']); print('client manifest ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard t3 bridge endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urlopen(f'http://127.0.0.1:{server.server_address[1]}/t3-bridge.json', timeout=5).read().decode('utf-8')); assert data['name'] == 'devframe-t3code-local-bridge'; assert data['target']['client'] == 't3code'; assert data['target']['license'] == 'MIT'; assert 'VITE_HTTP_URL' not in data['environment']; assert 'VITE_WS_URL' not in data['environment']; assert 'VITE_DEVFRAME_T3_SHELL_URL' not in data['environment']; assert data['environment']['VITE_DEVFRAME_REALTIME_MODE'] == 'polling'; assert data['environment']['VITE_DEVFRAME_CLIENT_PLAN_URL'].endswith('/client-plan.json'); assert data['environment']['VITE_DEVFRAME_CLIENT_MANIFEST_URL'].endswith('/client-manifest.json'); assert data['environment']['VITE_HOSTED_APP_CHANNEL'] == 'nightly'; assert any(file['path'] == 'apps/web/src/devframe/devframeShellBridge.ts' for file in data['files']); assert any(file['path'] == 'apps/web/src/connection/catalog.ts' and file['status'] == 'ready' for file in data['files']); assert any(file['path'] == 'apps/web/src/state/shell.ts' and file['status'] == 'ready' for file in data['files']); assert any(file['path'] == 'apps/web/src/state/threads.ts' and file['status'] == 'ready' for file in data['files']); assert data['integration']['strategy'] == 'reuse-t3-client-runtime-shell-and-thread-detail'; assert data['integration']['mutationPolicy'] == 'read-only'; print('t3 bridge ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard t3 environment descriptor" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urlopen(f'http://127.0.0.1:{server.server_address[1]}/.well-known/t3/environment', timeout=5).read().decode('utf-8')); assert data['environmentId'] == 'devframe-local'; assert data['label'] == 'DevFrame Local Agent Control Plane'; assert data['capabilities']['repositoryIdentity'] is False; print('t3 environment ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard t3 auth session" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import Request, urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); base = f'http://127.0.0.1:{server.server_address[1]}'; req = Request(base + '/api/auth/session', headers={'Origin': 'http://localhost:5733'}); resp = urlopen(req, timeout=5); data = json.loads(resp.read().decode('utf-8')); assert resp.headers['Access-Control-Allow-Origin'] == 'http://localhost:5733'; assert data['authenticated'] is True; assert data['auth']['policy'] == 'unsafe-no-auth'; assert data['scopes'] == ['orchestration:read']; preflight = Request(base + '/api/auth/session', method='OPTIONS', headers={'Origin': 'http://localhost:5733', 'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'b3, traceparent'}); options = urlopen(preflight, timeout=5); assert options.status == 204; assert 'GET' in options.headers['Access-Control-Allow-Methods']; assert 'b3' in options.headers['Access-Control-Allow-Headers']; assert 'traceparent' in options.headers['Access-Control-Allow-Headers']; print('t3 auth session ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard t3 shell endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urlopen(f'http://127.0.0.1:{server.server_address[1]}/t3-shell.json', timeout=5).read().decode('utf-8')); assert data['reuse']['client'] == 't3code'; assert data['reuse']['executor'] == 'opencode'; assert data['devframe']['writePolicy'] == 'read-only'; assert data['devframe']['manifest'] == '/client-manifest.json'; assert data['devframe']['controlPlaneBaseUrl'].startswith('http://127.0.0.1:'); assert len(data['t3']['projects']) >= 1; assert len(data['t3']['threads']) >= 1; assert len(data['t3']['threadDetails']) == len(data['t3']['threads']); assert all('actionDetails' in thread['devframe'] for thread in data['t3']['threads']); assert any(action.get('openUrl', '').startswith(data['devframe']['controlPlaneBaseUrl'] + '/actions/open?action_id=') for thread in data['t3']['threads'] for action in thread['devframe']['actionDetails']); assert any(thread['devframe']['provider'] == 'chatgpt' for thread in data['t3']['threads']); detail = data['t3']['threadDetails'][0]; assert detail['messages']; assert 'DevFrame Agent Session' in detail['messages'][0]['text']; assert detail['proposedPlans']; assert all(thread['session']['runtimeMode'] in {'approval-required', 'full-access'} for thread in data['t3']['threads']); print('t3 shell ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard actions endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urlopen(f'http://127.0.0.1:{server.server_address[1]}/actions.json?status=ready&source_type=run', timeout=5).read().decode('utf-8')); assert len(data['next_actions']) == 1; print(data['next_actions'][0]['source_id']); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard actions markdown endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); text = urlopen(f'http://127.0.0.1:{server.server_address[1]}/actions.md?status=ready&source_type=run', timeout=5).read().decode('utf-8'); assert '# Action Queue Handoff' in text; assert 'paper-project-paper-review-command-action' in text; assert 'devframe actions --action-id paper-project-paper-review-command-action --format markdown' in text; assert 'devframe run --pipeline' in text; print('actions.md ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard actions action-id endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); data = json.loads(urlopen(f'http://127.0.0.1:{server.server_address[1]}/actions.json?action_id=paper-project-paper-review-command-action', timeout=5).read().decode('utf-8')); text = urlopen(f'http://127.0.0.1:{server.server_address[1]}/actions.md?action_id=paper-project-paper-review-command-action', timeout=5).read().decode('utf-8'); assert len(data['next_actions']) == 1; assert 'paper-project-paper-review-command-action' in text; print(data['next_actions'][0]['action_id']); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard go dispatch endpoint" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.parse import urlencode; from urllib.request import Request, urlopen; import json, sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); base = f'http://127.0.0.1:{server.server_address[1]}'; html = urlopen(base + '/go/dispatch', timeout=5).read().decode('utf-8'); assert 'Dispatch /go coding agents' in html; assert sys.argv[3] in html; request = Request(base + '/go/dispatch', data=urlencode({'project_path': sys.argv[3], 'requirement': 'Wheel browser /go dispatch smoke.', 'targets': 'CURRENT_STATE.yaml', 'agents': '1', 'max_agents': '2', 'timeout': '30'}).encode('utf-8'), headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json', 'Origin': base}, method='POST'); payload = json.loads(urlopen(request, timeout=10).read().decode('utf-8')); assert payload['status'] == 'queued'; assert payload['agents'] == 1; assert payload['go_run_id'].startswith('go-demo-project-'); assert payload['execute'] is False; print(payload['go_run_id']); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir,
        $projectDir
    )
    $controlledActionProbe = @'
import json
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from control_plane.dashboard import build_dashboard_server

python_exe = sys.argv[1]
devframe_exe = sys.argv[2]
temp_root = Path(sys.argv[3])
project_root = temp_root / 'endpoint-project'
runtime_dir = temp_root / 'endpoint-runtime'
marker_path = temp_root / 'endpoint-marker.txt'
project_root.mkdir(parents=True, exist_ok=True)
(project_root / 'src.py').write_text("print('ok')\n", encoding='utf-8')
report_code = (
    'from pathlib import Path; import os; '
    f"Path({str(marker_path)!r}).write_text('ran', encoding='utf-8'); "
    "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
    "'## ExecutionReport\\n\\n"
    "- **Status**: pass\\n"
    "- **Changed Files**:\\n"
    "- (none)\\n"
    "- **Evidence**: controlled endpoint wheel smoke\\n', encoding='utf-8')"
)
subprocess.check_call([
    devframe_exe,
    'code',
    'Wheel controlled endpoint smoke.',
    '--project',
    str(project_root),
    '--runtime-dir',
    str(runtime_dir),
    '--agents',
    '1',
    '--target',
    'src.py',
    '--command',
    python_exe,
    '-c',
    report_code,
])
metadata_path = next((runtime_dir / 'go-runs').glob('*/go-run.json'))
metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
go_run_id = metadata['go_run_id']
action_id = f'{go_run_id}-execute-action'
server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f'http://127.0.0.1:{server.server_address[1]}'
try:
    html = urlopen(f'{base}/actions/open?action_id={action_id}', timeout=5).read().decode('utf-8')
    assert 'Start controlled execution' in html
    assert 'devframe code execute' in html
    try:
        urlopen(
            Request(
                f'{base}/actions/execute?action_id={action_id}',
                data=b'confirm=execute',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://example.com',
                },
                method='POST',
            ),
            timeout=5,
        )
    except HTTPError as exc:
        assert exc.code == 403
        assert 'same_origin_required' in exc.read().decode('utf-8')
    else:
        raise AssertionError('cross-origin execute unexpectedly succeeded')
    request = Request(
        f'{base}/actions/execute?action_id={action_id}',
        data=urlencode({'confirm': 'execute'}).encode('utf-8'),
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': base,
        },
        method='POST',
    )
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode('utf-8'))
        assert response.status == 202
    deadline = time.time() + 45
    final = {}
    while time.time() < deadline:
        final = json.loads(metadata_path.read_text(encoding='utf-8'))
        if final.get('status') in {'passed', 'failed', 'blocked'}:
            break
        time.sleep(0.5)
    assert payload['started'] is True
    assert payload['go_run_id'] == go_run_id
    assert final.get('status') == 'passed', final
    assert marker_path.read_text(encoding='utf-8') == 'ran'
    print('controlled action endpoint ok')
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
'@
    $controlledActionProbePath = Join-Path $tempRoot "controlled-action-probe.py"
    Set-Content -Path $controlledActionProbePath -Value $controlledActionProbe -Encoding utf8
    Invoke-Step "dashboard controlled action endpoint" $python @(
        $controlledActionProbePath,
        $python,
        $devframe,
        $tempRoot
    )
    Invoke-Step "dashboard actions invalid filter" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import build_opener, HTTPErrorProcessor; import sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); HTTPErrorProcessor.http_response = lambda self, request, response: response; HTTPErrorProcessor.https_response = HTTPErrorProcessor.http_response; response = build_opener(HTTPErrorProcessor).open(f'http://127.0.0.1:{server.server_address[1]}/actions.json?status=typo', timeout=5); assert response.status == 400; print(response.status); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )
    Invoke-Step "dashboard patch rejects" $python @(
        "-c",
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import build_opener, HTTPErrorProcessor, Request; import sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); HTTPErrorProcessor.http_response = lambda self, request, response: response; HTTPErrorProcessor.https_response = HTTPErrorProcessor.http_response; request = Request(f'http://127.0.0.1:{server.server_address[1]}/state.json', method='PATCH'); response = build_opener(HTTPErrorProcessor).open(request, timeout=5); assert response.status == 405; print(response.status); server.shutdown(); server.server_close(); thread.join(timeout=5)",
        $runtimeDir,
        $paperDir
    )

    Write-Output "[OK] Control-plane wheel smoke passed."
} finally {
    if (-not $KeepTemp -and (Test-Path -LiteralPath $tempRoot)) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
        Write-Output "[CLEAN] temp smoke directory"
    } elseif ($KeepTemp) {
        Write-Output "[KEEP] $tempRoot"
    }

    Remove-LocalBuildArtifacts
}
