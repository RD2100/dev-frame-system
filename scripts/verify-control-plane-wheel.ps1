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
        "import subprocess, sys; text = subprocess.check_output([sys.argv[1], '--help'], text=True); assert 'DevFrame Control Plane CLI' in text; assert 'devframe dashboard serve' in text; assert 'devframe actions' in text; print('devframe help ok')",
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
    Invoke-Step "devframe doctor" $devframe @("doctor")
    Invoke-Step "devframe init" $devframe @("init", "code_project", $projectDir)
    Invoke-Step "devframe init paper_iteration" $devframe @("init", "paper_iteration", $paperDir)
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
        "from control_plane.dashboard import build_dashboard_server; from threading import Thread; from urllib.request import urlopen; import sys; server = build_dashboard_server(runtime_dir=sys.argv[1], paper_project_dirs=[sys.argv[2]], port=0, refresh_seconds=0); thread = Thread(target=server.serve_forever, daemon=True); thread.start(); html = urlopen(f'http://127.0.0.1:{server.server_address[1]}/', timeout=5).read().decode('utf-8'); assert '/state.json' in html; assert '/actions.json' in html; assert '/actions.md' in html; assert 'actions.md?action_id=' in html; assert 'Gate Focus' in html; assert 'paper-project-privacy-gate' in html; assert 'paper-project-privacy-gate-action' in html; assert '/actions.md?action_id=paper-project-privacy-gate-action' in html; assert '<dt>Current Decision</dt>' in html; assert 'paper-project-paper-decision' in html; assert 'Complete the provider safety gate, then prepare the privacy-safe paper task packet.' in html; assert '<th>Provider</th>' in html; assert '<th>Binding Health</th>' in html; assert 'paper-reviewer-paper-project-chatgpt-web' in html; assert 'chatgpt' in html; assert 'needs_login' in html; assert '<th>Action ID</th>' in html; assert '<th>Resume Filter</th>' in html; assert '<th>Manual Fallback</th>' in html; assert 'Local agent writes a minimized prompt packet.' in html; assert 'paper-project-paper-review-command-action' in html; assert 'devframe actions --action-id paper-project-paper-review-command-action --format markdown' in html; print('dashboard links ok'); server.shutdown(); server.server_close(); thread.join(timeout=5)",
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
