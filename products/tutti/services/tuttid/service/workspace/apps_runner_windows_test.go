//go:build windows

package workspace

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	workspacebiz "github.com/tutti-os/tutti/services/tuttid/biz/workspace"
	tuttitypes "github.com/tutti-os/tutti/services/tuttid/types"
)

func TestAppRunnerWindowsPowerShellBootstrapNoPs1SiblingError(t *testing.T) {
	nodePath, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node is required for Windows PowerShell runner test")
	}

	root := t.TempDir()
	packageDir := filepath.Join(root, "my & (package) dir %")
	runtimeDir := filepath.Join(root, "runtime")
	dataDir := filepath.Join(root, "data")
	logDir := filepath.Join(root, "logs")
	for _, dir := range []string{packageDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("MkdirAll(%s) error = %v", dir, err)
		}
	}

	if err := os.WriteFile(filepath.Join(packageDir, "bootstrap.sh"), []byte("#!/bin/sh\necho ok\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("TUTTI_APP_NODE", nodePath)
	runner := &AppRunner{HealthcheckTimeout: 5 * time.Second}
	input := AppStartInput{
		WorkspaceID:     "ws-win-test",
		WorkspaceName:   "Win Test",
		WorkspaceRoot:   root,
		AppID:           "no-ps1",
		PackageDir:      packageDir,
		Bootstrap:       "bootstrap.sh",
		HealthcheckPath: "/healthz",
		RuntimeProfile:  workspaceAppStandaloneRuntimeProfile,
		RuntimeDir:      runtimeDir,
		DataDir:         dataDir,
		LogDir:          logDir,
	}
	state, startErr := runner.Start(context.Background(), input)
	if startErr != nil {
		t.Fatalf("Start() error = %v", startErr)
	}
	t.Cleanup(func() {
		_, _ = runner.Stop(context.Background(), "ws-win-test", "no-ps1")
	})
	state = waitForRunnerStatus(t, runner, "ws-win-test", "no-ps1", workspacebiz.AppRuntimeStatusFailed)
	if state.FailureReason == nil || *state.FailureReason != "startup" {
		t.Fatalf("FailureReason = %v, want startup", state.FailureReason)
	}
	if state.LastError == nil || !strings.Contains(*state.LastError, "does not exist") {
		t.Fatalf("LastError = %v, want missing file error (no .ps1 sibling)", state.LastError)
	}

	logData, err := os.ReadFile(filepath.Join(logDir, "runtime.log"))
	if err == nil {
		if strings.Contains(string(logData), "runner-started") || strings.Contains(string(logData), "#!/bin/sh") {
			t.Fatal(".sh side-effect detected before bootstrap resolution failure")
		}
	}
}

func TestAppRunnerWindowsPowerShellBootstrapSuccess(t *testing.T) {
	nodePath, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node is required for Windows PowerShell runner test")
	}

	root := t.TempDir()
	packageDir := filepath.Join(root, "my & (package) dir %")
	runtimeDir := filepath.Join(root, "runtime")
	dataDir := filepath.Join(root, "data")
	logDir := filepath.Join(root, "logs")
	for _, dir := range []string{packageDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("MkdirAll(%s) error = %v", dir, err)
		}
	}

	if err := os.WriteFile(filepath.Join(packageDir, "bootstrap.sh"), []byte("#!/bin/sh\necho ok\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	serverJS := `const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const host = process.env.TUTTI_APP_HOST || "127.0.0.1";
const port = parseInt(process.env.TUTTI_APP_PORT || "", 10);
const dataDir = process.env.TUTTI_APP_DATA_DIR;

const probe = {
  pid: process.pid,
  cwd: process.cwd(),
  appId: process.env.TUTTI_APP_ID || "",
  workspaceId: process.env.TUTTI_WORKSPACE_ID || "",
  workspaceName: process.env.TUTTI_WORKSPACE_NAME || "",
  workspaceRoot: process.env.TUTTI_WORKSPACE_ROOT || "",
  appHost: process.env.TUTTI_APP_HOST || "",
  appBaseUrl: process.env.TUTTI_APP_BASE_URL || "",
  packageDir: process.env.TUTTI_APP_PACKAGE_DIR || "",
  runtimeDir: process.env.TUTTI_APP_RUNTIME_DIR || "",
  dataDir: process.env.TUTTI_APP_DATA_DIR || "",
  logDir: process.env.TUTTI_APP_LOG_DIR || "",
};

if (dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(path.join(dataDir, "probe.json"), JSON.stringify(probe, null, 2), "utf8");
  fs.writeFileSync(path.join(dataDir, "pid.txt"), String(process.pid), "utf8");
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url || "/", "http://" + host + ":" + port);
  if (req.method === "GET" && u.pathname === "/healthz") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, pid: process.pid }));
    return;
  }
  res.writeHead(404);
  res.end("not found");
});
server.listen(port, host);
`
	if err := os.WriteFile(filepath.Join(packageDir, "server.js"), []byte(serverJS), 0o644); err != nil {
		t.Fatal(err)
	}

	bootstrapPS1 := `$ErrorActionPreference = "Stop"
$pidPath = Join-Path $env:TUTTI_APP_DATA_DIR "parent_pid.txt"
[System.IO.File]::WriteAllText($pidPath, "$PID")
& $env:TUTTI_APP_NODE "$env:TUTTI_APP_PACKAGE_DIR\server.js"
`
	if err := os.WriteFile(filepath.Join(packageDir, "bootstrap.ps1"), []byte(bootstrapPS1), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("TUTTI_APP_NODE", nodePath)
	runner := &AppRunner{HealthcheckTimeout: 15 * time.Second}
	input := AppStartInput{
		WorkspaceID:     "ws-win-test",
		WorkspaceName:   "Win Test",
		WorkspaceRoot:   root,
		AppID:           "ps1-app",
		PackageDir:      packageDir,
		Bootstrap:       "bootstrap.sh",
		HealthcheckPath: "/healthz",
		RuntimeProfile:  workspaceAppStandaloneRuntimeProfile,
		RuntimeDir:      runtimeDir,
		DataDir:         dataDir,
		LogDir:          logDir,
	}
	state, startErr := runner.Start(context.Background(), input)
	if startErr != nil {
		t.Fatalf("Start() error = %v", startErr)
	}
	t.Cleanup(func() {
		_, _ = runner.Stop(context.Background(), "ws-win-test", "ps1-app")
	})
	if state.Status != workspacebiz.AppRuntimeStatusPreparing {
		t.Fatalf("Start() status = %q, want preparing", state.Status)
	}

	state = waitForRunnerStatus(t, runner, "ws-win-test", "ps1-app", workspacebiz.AppRuntimeStatusRunning)
	if state.LaunchURL == nil || !strings.HasPrefix(*state.LaunchURL, "http://127.0.0.1:") {
		t.Fatalf("LaunchURL = %v", state.LaunchURL)
	}

	parentPidRaw, err := os.ReadFile(filepath.Join(dataDir, "parent_pid.txt"))
	if err != nil {
		t.Fatalf("ReadFile(parent_pid.txt) error = %v", err)
	}
	parentPid, err := strconv.Atoi(strings.TrimSpace(string(parentPidRaw)))
	if err != nil {
		t.Fatalf("Parse(parent_pid) error = %v", err)
	}
	if parentPid <= 0 {
		t.Fatalf("parent_pid = %d, want positive", parentPid)
	}
	if !isWindowsProcessRunning(parentPid) {
		t.Fatalf("parent PowerShell pid %d is not running", parentPid)
	}

	childPidRaw, err := os.ReadFile(filepath.Join(dataDir, "pid.txt"))
	if err != nil {
		t.Fatalf("ReadFile(pid.txt) error = %v", err)
	}
	childPid, err := strconv.Atoi(strings.TrimSpace(string(childPidRaw)))
	if err != nil {
		t.Fatalf("Parse(child_pid) error = %v", err)
	}
	if childPid <= 0 || childPid == parentPid {
		t.Fatalf("child_pid = %d, want positive and different from parent %d", childPid, parentPid)
	}
	if !isWindowsProcessRunning(childPid) {
		t.Fatalf("child Node pid %d is not running", childPid)
	}

	probeRaw, err := os.ReadFile(filepath.Join(dataDir, "probe.json"))
	if err != nil {
		t.Fatalf("ReadFile(probe.json) error = %v", err)
	}
	var probe map[string]interface{}
	if err := json.Unmarshal(probeRaw, &probe); err != nil {
		t.Fatalf("Unmarshal(probe.json) error = %v", err)
	}
	if got, ok := probe["packageDir"].(string); !ok || got != packageDir {
		t.Fatalf("probe packageDir = %v, want %q", probe["packageDir"], packageDir)
	}
	if got, ok := probe["runtimeDir"].(string); !ok || got != runtimeDir {
		t.Fatalf("probe runtimeDir = %v, want %q", probe["runtimeDir"], runtimeDir)
	}
	if got, ok := probe["dataDir"].(string); !ok || got != dataDir {
		t.Fatalf("probe dataDir = %v, want %q", probe["dataDir"], dataDir)
	}

	stopped, stopErr := runner.Stop(context.Background(), "ws-win-test", "ps1-app")
	if stopErr != nil {
		t.Fatalf("Stop() error = %v", stopErr)
	}
	if stopped.Status != workspacebiz.AppRuntimeStatusIdle {
		t.Fatalf("Stop() status = %q, want idle", stopped.Status)
	}

	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if !isWindowsProcessRunning(parentPid) && !isWindowsProcessRunning(childPid) {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	if isWindowsProcessRunning(parentPid) {
		t.Errorf("parent PowerShell pid %d still running after stop", parentPid)
	}
	if isWindowsProcessRunning(childPid) {
		t.Errorf("child Node pid %d still running after stop", childPid)
	}
	t.Fatal("processes did not exit after stop within timeout")
}

func TestAppRunnerWindowsRestartExitsOldChildAndProducesNewPid(t *testing.T) {
	nodePath, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node is required for Windows PowerShell runner test")
	}

	root := t.TempDir()
	packageDir := filepath.Join(root, "restart-test")
	runtimeDir := filepath.Join(root, "runtime")
	dataDir := filepath.Join(root, "data")
	logDir := filepath.Join(root, "logs")
	for _, dir := range []string{packageDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("MkdirAll(%s) error = %v", dir, err)
		}
	}

	serverJS := `const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const host = process.env.TUTTI_APP_HOST || "127.0.0.1";
const port = parseInt(process.env.TUTTI_APP_PORT || "", 10);
const dataDir = process.env.TUTTI_APP_DATA_DIR;

if (dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(path.join(dataDir, "pid.txt"), String(process.pid), "utf8");
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url || "/", "http://" + host + ":" + port);
  if (u.pathname === "/healthz") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, pid: process.pid }));
    return;
  }
  res.writeHead(404);
  res.end("not found");
});
server.listen(port, host);
`
	if err := os.WriteFile(filepath.Join(packageDir, "server.js"), []byte(serverJS), 0o644); err != nil {
		t.Fatal(err)
	}

	bootstrapPS1 := `$ErrorActionPreference = "Stop"
& $env:TUTTI_APP_NODE "$env:TUTTI_APP_PACKAGE_DIR\server.js"
`
	if err := os.WriteFile(filepath.Join(packageDir, "bootstrap.ps1"), []byte(bootstrapPS1), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("TUTTI_APP_NODE", nodePath)
	runner := &AppRunner{HealthcheckTimeout: 15 * time.Second}
	input := AppStartInput{
		WorkspaceID:     "ws-win-test",
		WorkspaceName:   "Win Test",
		WorkspaceRoot:   root,
		AppID:           "restart-app",
		PackageDir:      packageDir,
		Bootstrap:       "bootstrap.ps1",
		HealthcheckPath: "/healthz",
		RuntimeProfile:  workspaceAppStandaloneRuntimeProfile,
		RuntimeDir:      runtimeDir,
		DataDir:         dataDir,
		LogDir:          logDir,
	}
	_, err = runner.Start(context.Background(), input)
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = runner.Stop(context.Background(), "ws-win-test", "restart-app")
	})
	waitForRunnerStatus(t, runner, "ws-win-test", "restart-app", workspacebiz.AppRuntimeStatusRunning)

	firstPidRaw, _ := os.ReadFile(filepath.Join(dataDir, "pid.txt"))
	firstPid, _ := strconv.Atoi(strings.TrimSpace(string(firstPidRaw)))
	if firstPid <= 0 {
		t.Fatalf("first pid = %d, want positive", firstPid)
	}

	input.Restart = true
	_, err = runner.Start(context.Background(), input)
	if err != nil {
		t.Fatalf("Start(Restart) error = %v", err)
	}
	waitForRunnerStatus(t, runner, "ws-win-test", "restart-app", workspacebiz.AppRuntimeStatusRunning)

	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if !isWindowsProcessRunning(firstPid) {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if isWindowsProcessRunning(firstPid) {
		t.Fatalf("old child pid %d still running after restart", firstPid)
	}

	secondPidRaw, _ := os.ReadFile(filepath.Join(dataDir, "pid.txt"))
	secondPid, _ := strconv.Atoi(strings.TrimSpace(string(secondPidRaw)))
	if secondPid <= 0 || secondPid == firstPid {
		t.Fatalf("restart child pid: first=%d second=%d, want different", firstPid, secondPid)
	}
}

func TestAppRunnerWindowsPowerShellExplicitPs1Runs(t *testing.T) {
	nodePath, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node is required for Windows PowerShell runner test")
	}

	root := t.TempDir()
	packageDir := filepath.Join(root, "package")
	runtimeDir := filepath.Join(root, "runtime")
	dataDir := filepath.Join(root, "data")
	logDir := filepath.Join(root, "logs")
	for _, dir := range []string{packageDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("MkdirAll(%s) error = %v", dir, err)
		}
	}

	serverJS := `const http = require("node:http");
const host = process.env.TUTTI_APP_HOST || "127.0.0.1";
const port = parseInt(process.env.TUTTI_APP_PORT || "", 10);
const server = http.createServer((req, res) => {
  const u = new URL(req.url || "/", "http://" + host + ":" + port);
  if (u.pathname === "/healthz") { res.writeHead(200); res.end("ok"); return; }
  res.writeHead(404); res.end();
});
server.listen(port, host);
`
	if err := os.WriteFile(filepath.Join(packageDir, "server.js"), []byte(serverJS), 0o644); err != nil {
		t.Fatal(err)
	}

	bootstrapPS1 := `$ErrorActionPreference = "Stop"
& $env:TUTTI_APP_NODE "$env:TUTTI_APP_PACKAGE_DIR\server.js"
`
	if err := os.WriteFile(filepath.Join(packageDir, "explicit-boot.ps1"), []byte(bootstrapPS1), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("TUTTI_APP_NODE", nodePath)
	runner := &AppRunner{HealthcheckTimeout: 15 * time.Second}
	state, err := runner.Start(context.Background(), AppStartInput{
		WorkspaceID:     "ws-win-test",
		WorkspaceName:   "Win Test",
		WorkspaceRoot:   root,
		AppID:           "explicit-ps1",
		PackageDir:      packageDir,
		Bootstrap:       "explicit-boot.ps1",
		HealthcheckPath: "/healthz",
		RuntimeProfile:  workspaceAppStandaloneRuntimeProfile,
		RuntimeDir:      runtimeDir,
		DataDir:         dataDir,
		LogDir:          logDir,
	})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = runner.Stop(context.Background(), "ws-win-test", "explicit-ps1")
	})
	if state.Status != workspacebiz.AppRuntimeStatusPreparing {
		t.Fatalf("Start() status = %q, want preparing", state.Status)
	}
	waitForRunnerStatus(t, runner, "ws-win-test", "explicit-ps1", workspacebiz.AppRuntimeStatusRunning)

	stopped, err := runner.Stop(context.Background(), "ws-win-test", "explicit-ps1")
	if err != nil {
		t.Fatalf("Stop() error = %v", err)
	}
	if stopped.Status != workspacebiz.AppRuntimeStatusIdle {
		t.Fatalf("Stop() status = %q, want idle", stopped.Status)
	}
}

func TestAppRunnerWindowsRejectsCmdBootstrap(t *testing.T) {
	nodePath, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node is required for Windows test")
	}

	root := t.TempDir()
	packageDir := filepath.Join(root, "package")
	runtimeDir := filepath.Join(root, "runtime")
	dataDir := filepath.Join(root, "data")
	logDir := filepath.Join(root, "logs")
	for _, dir := range []string{packageDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("MkdirAll(%s) error = %v", dir, err)
		}
	}

	if err := os.WriteFile(filepath.Join(packageDir, "bootstrap.cmd"), []byte("@echo ok"), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("TUTTI_APP_NODE", nodePath)
	runner := &AppRunner{HealthcheckTimeout: 5 * time.Second}
	state, _ := runner.Start(context.Background(), AppStartInput{
		WorkspaceID:     "ws-win-test",
		AppID:           "cmd-reject",
		PackageDir:      packageDir,
		Bootstrap:       "bootstrap.cmd",
		HealthcheckPath: "/healthz",
		RuntimeProfile:  workspaceAppStandaloneRuntimeProfile,
		RuntimeDir:      runtimeDir,
		DataDir:         dataDir,
		LogDir:          logDir,
	})
	state = waitForRunnerStatus(t, runner, "ws-win-test", "cmd-reject", workspacebiz.AppRuntimeStatusFailed)
	if state.FailureReason == nil || *state.FailureReason != "startup" {
		t.Fatalf("FailureReason = %v, want startup", state.FailureReason)
	}
	if state.LastError == nil || !strings.Contains(*state.LastError, "unsupported") {
		t.Fatalf("LastError = %v, want unsupported extension error", state.LastError)
	}
}

func TestAppRunnerWindowsRejectsTraversalBootstrap(t *testing.T) {
	nodePath, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node is required for Windows test")
	}

	root := t.TempDir()
	packageDir := filepath.Join(root, "package")
	outsideDir := filepath.Join(root, "outside")
	runtimeDir := filepath.Join(root, "runtime")
	dataDir := filepath.Join(root, "data")
	logDir := filepath.Join(root, "logs")
	for _, dir := range []string{packageDir, outsideDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("MkdirAll(%s) error = %v", dir, err)
		}
	}

	if err := os.WriteFile(filepath.Join(outsideDir, "out.ps1"), []byte("exit 0\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("TUTTI_APP_NODE", nodePath)
	runner := &AppRunner{HealthcheckTimeout: 5 * time.Second}
	state, _ := runner.Start(context.Background(), AppStartInput{
		WorkspaceID:     "ws-win-test",
		AppID:           "traversal",
		PackageDir:      packageDir,
		Bootstrap:       "../outside/out.ps1",
		HealthcheckPath: "/healthz",
		RuntimeProfile:  workspaceAppStandaloneRuntimeProfile,
		RuntimeDir:      runtimeDir,
		DataDir:         dataDir,
		LogDir:          logDir,
	})
	state = waitForRunnerStatus(t, runner, "ws-win-test", "traversal", workspacebiz.AppRuntimeStatusFailed)
	if state.FailureReason == nil || *state.FailureReason != "startup" {
		t.Fatalf("FailureReason = %v, want startup", state.FailureReason)
	}
	if state.LastError == nil || !strings.Contains(*state.LastError, "relative") {
		t.Fatalf("LastError = %v, want relative path error", state.LastError)
	}
}

func isWindowsProcessRunning(pid int) bool {
	return tuttitypes.ProcessExists(pid)
}
