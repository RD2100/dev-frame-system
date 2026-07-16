package agentstatus

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"

	externalagentregistry "github.com/tutti-os/tutti/services/tuttid/service/externalagentregistry"
	managedruntime "github.com/tutti-os/tutti/services/tuttid/service/managedruntime"
)

func TestDisplayNPMRegistryStripsCredentials(t *testing.T) {
	t.Parallel()

	cases := map[string]string{
		// Plain registries (and the test override) pass through unchanged.
		"https://registry.npmjs.org":    "https://registry.npmjs.org",
		"https://registry.example.test": "https://registry.example.test",
		"registry.example.test":         "registry.example.test",
		// Embedded credentials are stripped before status/log exposure.
		"https://user:token@registry.foo/path": "https://registry.foo/path",
		"https://token@registry.foo":           "https://registry.foo",
	}
	for in, want := range cases {
		if got := displayNPMRegistry(in); got != want {
			t.Errorf("displayNPMRegistry(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestCodexNPMPrefixFromPackageDir(t *testing.T) {
	t.Parallel()

	cases := map[string]string{
		// Unix npm global layout: <prefix>/lib/node_modules/@openai/codex
		filepath.Join("/Users/x/.nvm/versions/node/v24.12.0", "lib", "node_modules", "@openai", "codex"): "/Users/x/.nvm/versions/node/v24.12.0",
		filepath.Join("/Users/x/.local", "lib", "node_modules", "@openai", "codex"):                      "/Users/x/.local",
		filepath.Join("/usr/local", "lib", "node_modules", "@openai", "codex"):                           "/usr/local",
		// Windows npm global layout: <prefix>/node_modules/@openai/codex (no lib)
		filepath.Join("C:/Users/x/AppData/Roaming/npm", "node_modules", "@openai", "codex"): "C:/Users/x/AppData/Roaming/npm",
		// Not npm's global layout -> no prefix derivable.
		filepath.Join("/tmp/standalone/codex"): "",
		"/node_modules/@openai/codex":          "",
	}
	for in, want := range cases {
		if got := npmGlobalPrefixFromPackageDir(in); got != want {
			t.Errorf("npmGlobalPrefixFromPackageDir(%q) = %q, want %q", in, got, want)
		}
	}
}

// TestRunCodexCLILatestInstallerRepairsInPlace verifies that when an existing
// @openai/codex install is resolved but incomplete, the installer reinstalls
// into the npm global prefix that already owns it (repair-in-place) rather than
// duplicating the package in ~/.local.
func TestRunCodexCLILatestInstallerRepairsInPlace(t *testing.T) {
	home := t.TempDir()
	// Mimic an nvm-style global install with a missing platform subpackage.
	nvmPrefix := filepath.Join(home, ".nvm", "versions", "node", "v24.12.0")
	pkgDir := filepath.Join(nvmPrefix, "lib", "node_modules", "@openai", "codex")
	writePackageManifest(t, pkgDir, "@openai/codex", MinSupportedCodexVersion)
	codexBin := filepath.Join(pkgDir, "bin", "codex")
	writeExecutable(t, codexBin, "#!/bin/sh\nexit 0\n")
	binDir := filepath.Join(nvmPrefix, "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatalf("mkdir bin dir: %v", err)
	}
	if err := os.Symlink(codexBin, filepath.Join(binDir, "codex")); err != nil {
		t.Fatalf("symlink codex: %v", err)
	}
	// Fake npm/node on PATH so the resolver finds them.
	writeExecutable(t, filepath.Join(binDir, npmBinaryNameForTest()), "#!/bin/sh\nexit 0\n")
	writeExecutable(t, filepath.Join(binDir, nodeBinaryNameForTest()), "#!/bin/sh\nexit 0\n")
	setupNPMCLIJS(t, binDir)

	service := probeTestService(home)
	service.HTTPClient = agentNPMRegistryProbeHTTPClient(nil)
	service.Environ = func() []string { return []string{"PATH=" + binDir} }
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	existingCLIPath := filepath.Join(binDir, "codex")
	wantPrefix, wantPrefixOK := managedNPMRepairInstallPrefix(existingCLIPath, "@openai/codex")
	if !wantPrefixOK {
		t.Fatalf("expected repair prefix to be derivable for %s", existingCLIPath)
	}

	var command InstallCommandInput
	service.InstallCommand = func(_ context.Context, input InstallCommandInput) (InstallCommandResult, error) {
		command = input
		return InstallCommandResult{ExitCode: 0, Stdout: "repaired"}, nil
	}

	if _, err := service.runCodexCLILatestInstaller(context.Background(), InstallerSpec{
		Kind:     InstallerKindCodexCLILatest,
		CodexCLI: &CodexCLILatestInstallerSpec{},
	}, existingCLIPath); err != nil {
		t.Fatalf("runCodexCLILatestInstaller() error = %v", err)
	}
	if !strings.Contains(command.Command, "--prefix "+wantPrefix+" ") {
		t.Fatalf("Command = %q, want repair-in-place at --prefix %s", command.Command, wantPrefix)
	}
	if strings.Contains(command.Command, filepath.Join(home, ".local")) {
		t.Fatalf("Command = %q, repair-in-place must not duplicate the package in ~/.local", command.Command)
	}
}

// TestRunCodexCLILatestInstallerFallsBackToLocalBin verifies that when the
// existing codex binary is not from an npm global install (no package layout to
// derive a prefix from), the installer falls back to a fresh install in ~/.local.
func TestRunCodexCLILatestInstallerFallsBackToLocalBin(t *testing.T) {
	home := t.TempDir()
	binDir := filepath.Join(home, "bin")
	// Standalone codex binary with no @openai/codex package.json above it.
	standalone := filepath.Join(binDir, "codex")
	writeExecutable(t, standalone, "#!/bin/sh\nexit 0\n")
	writeExecutable(t, filepath.Join(binDir, npmBinaryNameForTest()), "#!/bin/sh\nexit 0\n")
	writeExecutable(t, filepath.Join(binDir, nodeBinaryNameForTest()), "#!/bin/sh\nexit 0\n")
	setupNPMCLIJS(t, binDir)

	service := probeTestService(home)
	service.HTTPClient = agentNPMRegistryProbeHTTPClient(nil)
	service.Environ = func() []string { return []string{"PATH=" + binDir} }
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	if _, ok := managedNPMRepairInstallPrefix(standalone, "@openai/codex"); ok {
		t.Fatalf("standalone codex should not yield a repair prefix")
	}

	var command InstallCommandInput
	service.InstallCommand = func(_ context.Context, input InstallCommandInput) (InstallCommandResult, error) {
		command = input
		return InstallCommandResult{ExitCode: 0, Stdout: "installed"}, nil
	}

	if _, err := service.runCodexCLILatestInstaller(context.Background(), InstallerSpec{
		Kind:     InstallerKindCodexCLILatest,
		CodexCLI: &CodexCLILatestInstallerSpec{},
	}, standalone); err != nil {
		t.Fatalf("runCodexCLILatestInstaller() error = %v", err)
	}
	installBinDir := filepath.Join(home, ".local", "bin")
	wantPrefix := filepath.Dir(installBinDir)
	if runtime.GOOS == "windows" {
		wantPrefix = installBinDir
	}
	if !strings.Contains(command.Command, "--prefix") || !strings.Contains(command.Command, wantPrefix) {
		t.Fatalf("Command = %q, want fresh install at --prefix %s", command.Command, wantPrefix)
	}
	if !strings.Contains(command.Command, "--prefix "+wantPrefix+" ") && !strings.Contains(command.Command, "--prefix '"+wantPrefix+"' ") {
		t.Fatalf("Command = %q, want fresh install at --prefix %s", command.Command, wantPrefix)
	}
}

func TestRunCodexCLILatestInstallerUsesManagedRuntimeNPMWhenUserNPMMissing(t *testing.T) {
	home := t.TempDir()
	runtimeRoot := fakeManagedRuntimeRoot(t)
	managedNPM := filepath.Join(runtimeRoot, "node", "bin", npmBinaryNameForTest())
	managedNode := filepath.Join(runtimeRoot, "node", "bin", nodeBinaryNameForTest())
	managedNodeBinDir := filepath.Dir(managedNode)

	service := probeTestService(home)
	service.HTTPClient = agentNPMRegistryProbeHTTPClient(nil)
	service.Environ = func() []string {
		return []string{"PATH=/usr/bin:/bin", agentNPMRegistryEnv + "=https://registry.example.test"}
	}
	service.ManagedRuntime = staticManagedRuntimeResolver{
		runtime: managedruntime.ResolvedRuntime{
			Root:    runtimeRoot,
			Node:    managedNode,
			NPM:     managedNPM,
			BinDirs: []string{managedNodeBinDir},
			EnvOverrides: []string{
				"TUTTI_APP_RUNTIME_ROOT=" + runtimeRoot,
				"TUTTI_APP_NODE=" + managedNode,
				"TUTTI_APP_NPM=" + managedNPM,
				"PATH=" + managedNodeBinDir + string(os.PathListSeparator) + "/usr/bin" + string(os.PathListSeparator) + "/bin",
			},
		},
	}
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	var command InstallCommandInput
	service.InstallCommand = func(_ context.Context, input InstallCommandInput) (InstallCommandResult, error) {
		command = input
		return InstallCommandResult{ExitCode: 0, Stdout: "installed"}, nil
	}

	if _, err := service.runCodexCLILatestInstaller(context.Background(), InstallerSpec{
		Kind:     InstallerKindCodexCLILatest,
		CodexCLI: &CodexCLILatestInstallerSpec{},
	}, ""); err != nil {
		t.Fatalf("runCodexCLILatestInstaller() error = %v", err)
	}
	if !strings.Contains(command.Command, managedNPM) ||
		!strings.Contains(command.Command, "install") ||
		!strings.Contains(command.Command, "@openai/codex") ||
		!strings.Contains(command.Command, "--include=optional") ||
		!strings.Contains(command.Command, "--prefix") {
		t.Fatalf("Command = %q, want managed runtime npm install", command.Command)
	}
	if !slices.Contains(command.Env, "TUTTI_APP_NPM="+managedNPM) {
		t.Fatalf("Env = %#v, want managed runtime npm marker", command.Env)
	}
	if !slices.Contains(command.Env, "TUTTI_APP_NODE="+managedNode) {
		t.Fatalf("Env = %#v, want managed runtime node marker", command.Env)
	}
	if !slices.Contains(command.Env, "npm_config_registry=https://registry.example.test") {
		t.Fatalf("Env = %#v, want selected npm registry", command.Env)
	}
}

func TestRunManagedNPMPackageInstallerInstallsTuttiAgentWithManagedRuntime(t *testing.T) {
	home := t.TempDir()
	runtimeRoot := fakeManagedRuntimeRoot(t)
	managedNPM := filepath.Join(runtimeRoot, "node", "bin", npmBinaryNameForTest())
	managedNode := filepath.Join(runtimeRoot, "node", "bin", nodeBinaryNameForTest())
	managedNodeBinDir := filepath.Dir(managedNode)

	service := probeTestService(home)
	service.HTTPClient = agentNPMRegistryProbeHTTPClient(nil)
	service.Environ = func() []string {
		return []string{"PATH=/usr/bin:/bin", agentNPMRegistryEnv + "=https://registry.example.test"}
	}
	service.ManagedRuntime = staticManagedRuntimeResolver{
		runtime: managedruntime.ResolvedRuntime{
			Root:    runtimeRoot,
			Node:    managedNode,
			NPM:     managedNPM,
			BinDirs: []string{managedNodeBinDir},
			EnvOverrides: []string{
				"TUTTI_APP_RUNTIME_ROOT=" + runtimeRoot,
				"TUTTI_APP_NODE=" + managedNode,
				"TUTTI_APP_NPM=" + managedNPM,
				"PATH=" + managedNodeBinDir + string(os.PathListSeparator) + "/usr/bin" + string(os.PathListSeparator) + "/bin",
			},
		},
	}
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	var command InstallCommandInput
	service.InstallCommand = func(_ context.Context, input InstallCommandInput) (InstallCommandResult, error) {
		command = input
		return InstallCommandResult{ExitCode: 0, Stdout: "installed"}, nil
	}

	if _, err := service.runManagedNPMPackageInstaller(context.Background(), "tutti-agent", ManagedNPMPackageInstallerSpec{
		PackageName:     "@tutti-os/tutti-agent",
		BinaryName:      "tutti-agent",
		IncludeOptional: true,
	}, ""); err != nil {
		t.Fatalf("runManagedNPMPackageInstaller() error = %v", err)
	}
	if !strings.Contains(command.Command, managedNPM) ||
		!strings.Contains(command.Command, "install") ||
		!strings.Contains(command.Command, "@tutti-os/tutti-agent") ||
		!strings.Contains(command.Command, "--include=optional") ||
		!strings.Contains(command.Command, "--prefix") {
		t.Fatalf("Command = %q, want managed runtime npm install", command.Command)
	}
	if !slices.Contains(command.Env, "TUTTI_APP_NPM="+managedNPM) {
		t.Fatalf("Env = %#v, want managed runtime npm marker", command.Env)
	}
	if !slices.Contains(command.Env, "TUTTI_APP_NODE="+managedNode) {
		t.Fatalf("Env = %#v, want managed runtime node marker", command.Env)
	}
	if !slices.Contains(command.Env, "npm_config_registry=https://registry.example.test") {
		t.Fatalf("Env = %#v, want selected npm registry", command.Env)
	}
}

type staticManagedRuntimeResolver struct {
	runtime managedruntime.ResolvedRuntime
}

func (r staticManagedRuntimeResolver) Resolve(context.Context) (managedruntime.ResolvedRuntime, error) {
	return r.runtime, nil
}

func (r staticManagedRuntimeResolver) ResolveProfile(context.Context, string) (managedruntime.ResolvedRuntime, error) {
	return r.runtime, nil
}

func TestRunArgvInstallCommand(t *testing.T) {
	t.Parallel()

	var echoCmd string
	var echoArgs []string
	if runtime.GOOS == "windows" {
		echoCmd = "cmd.exe"
		echoArgs = []string{"/C", "echo", "hello", "world"}
	} else {
		echoCmd = "echo"
		echoArgs = []string{"hello", "world"}
	}
	args := append([]string{echoCmd}, echoArgs...)

	result, err := runArgvInstallCommand(context.Background(), InstallCommandInput{
		Args: args,
	})
	if err != nil {
		t.Fatalf("runArgvInstallCommand() error = %v", err)
	}
	if result.ExitCode != 0 {
		t.Fatalf("ExitCode = %d, want 0; stderr=%q", result.ExitCode, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "hello world") && !strings.Contains(result.Stdout, "hello") {
		t.Fatalf("Stdout = %q, want hello world", result.Stdout)
	}
}

func TestRunArgvInstallCommandWithCWD(t *testing.T) {
	t.Parallel()

	tmp := t.TempDir()
	var echoCmd string
	var echoArgs []string
	if runtime.GOOS == "windows" {
		echoCmd = "cmd.exe"
		echoArgs = []string{"/C", "cd"}
	} else {
		echoCmd = "pwd"
		echoArgs = nil
	}
	args := append([]string{echoCmd}, echoArgs...)

	result, err := runArgvInstallCommand(context.Background(), InstallCommandInput{
		Args: args,
		CWD:  tmp,
	})
	if err != nil {
		t.Fatalf("runArgvInstallCommand() error = %v", err)
	}
	if result.ExitCode != 0 {
		t.Fatalf("ExitCode = %d, want 0; stderr=%q", result.ExitCode, result.Stderr)
	}
}

func TestRunArgvInstallCommandEmptyArgs(t *testing.T) {
	t.Parallel()

	result, err := runArgvInstallCommand(context.Background(), InstallCommandInput{})
	if err == nil {
		t.Fatalf("runArgvInstallCommand() expected error for empty args, got result=%#v", result)
	}
}

func TestResolveManagedNPMNativeExeFindsNativeExeOnWindows(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific native exe resolution test")
	}

	home := t.TempDir()
	prefixBin := filepath.Join(home, ".local", "bin")
	pkgDir := filepath.Join(prefixBin, "node_modules", "opencode-ai")
	binDir := filepath.Join(pkgDir, "bin")
	exePath := filepath.Join(binDir, "opencode.exe")

	writePackageManifestWithBin(t, pkgDir, "opencode-ai", "1.17.18", "opencode", "./bin/opencode.exe")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatalf("mkdir bin: %v", err)
	}
	if err := os.WriteFile(exePath, []byte("fake-exe"), 0o755); err != nil {
		t.Fatalf("write exe: %v", err)
	}

	service := probeTestService(home)
	service.Environ = func() []string {
		return []string{"PATH=" + prefixBin}
	}
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	spec := ManagedNPMPackageInstallerSpec{
		PackageName: "opencode-ai",
		BinaryName:  "opencode",
	}
	env := service.commandResolver().Env(nil)
	resolved := service.resolveManagedNPMNativeExe(spec, env)
	if resolved != exePath {
		t.Fatalf("resolveManagedNPMNativeExe() = %q, want %q", resolved, exePath)
	}
}

func TestResolveManagedNPMNativeExeRejectsEscapeOutsidePackage(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific escape rejection test")
	}

	home := t.TempDir()
	prefixBin := filepath.Join(home, ".local", "bin")
	pkgDir := filepath.Join(prefixBin, "node_modules", "opencode-ai")

	writePackageManifestWithBin(t, pkgDir, "opencode-ai", "1.17.18", "opencode", `..\..\..\..\escaped.exe`)
	escapedExe := filepath.Join(home, "escaped.exe")
	if err := os.WriteFile(escapedExe, []byte("escaped"), 0o755); err != nil {
		t.Fatalf("write escaped exe: %v", err)
	}

	service := probeTestService(home)
	service.Environ = func() []string {
		return []string{"PATH=" + prefixBin}
	}

	spec := ManagedNPMPackageInstallerSpec{
		PackageName: "opencode-ai",
		BinaryName:  "opencode",
	}
	env := service.commandResolver().Env(nil)
	resolved := service.resolveManagedNPMNativeExe(spec, env)
	if resolved != "" {
		t.Fatalf("resolveManagedNPMNativeExe() = %q, want empty (escape rejected)", resolved)
	}
}

func TestResolveManagedNPMNativeExeRejectsSymlinkEscape(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific symlink escape rejection test")
	}

	home := t.TempDir()
	prefixBin := filepath.Join(home, ".local", "bin")
	pkgDir := filepath.Join(prefixBin, "node_modules", "opencode-ai")
	binDir := filepath.Join(pkgDir, "bin")

	writePackageManifestWithBin(t, pkgDir, "opencode-ai", "1.17.18", "opencode", "./bin/opencode.exe")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatalf("mkdir bin: %v", err)
	}

	outsideExe := filepath.Join(home, "outside.exe")
	if err := os.WriteFile(outsideExe, []byte("outside"), 0o755); err != nil {
		t.Fatalf("write outside exe: %v", err)
	}

	junctionTarget := filepath.Join(binDir, "opencode.exe")
	if err := os.Symlink(outsideExe, junctionTarget); err != nil {
		t.Skipf("cannot create symlink (may need admin): %v", err)
	}

	service := probeTestService(home)
	service.Environ = func() []string {
		return []string{"PATH=" + prefixBin}
	}

	spec := ManagedNPMPackageInstallerSpec{
		PackageName: "opencode-ai",
		BinaryName:  "opencode",
	}
	env := service.commandResolver().Env(nil)
	resolved := service.resolveManagedNPMNativeExe(spec, env)
	if resolved != "" {
		t.Fatalf("resolveManagedNPMNativeExe() = %q, want empty (symlink escape rejected)", resolved)
	}
}

func TestResolveManagedNPMNativeExeRejectsMissingPackage(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific missing package test")
	}

	home := t.TempDir()
	prefixBin := filepath.Join(home, ".local", "bin")

	service := probeTestService(home)
	service.Environ = func() []string {
		return []string{"PATH=" + prefixBin}
	}

	spec := ManagedNPMPackageInstallerSpec{
		PackageName: "opencode-ai",
		BinaryName:  "opencode",
	}
	env := service.commandResolver().Env(nil)
	resolved := service.resolveManagedNPMNativeExe(spec, env)
	if resolved != "" {
		t.Fatalf("resolveManagedNPMNativeExe() = %q, want empty (package not installed)", resolved)
	}
}

func TestResolveManagedNPMAdapterCommandSwapsCommandOnWindows(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific adapter command resolution test")
	}

	home := t.TempDir()
	prefixBin := filepath.Join(home, ".local", "bin")
	pkgDir := filepath.Join(prefixBin, "node_modules", "opencode-ai")
	binDir := filepath.Join(pkgDir, "bin")
	exePath := filepath.Join(binDir, "opencode.exe")

	writePackageManifestWithBin(t, pkgDir, "opencode-ai", "1.17.18", "opencode", "./bin/opencode.exe")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatalf("mkdir bin: %v", err)
	}
	if err := os.WriteFile(exePath, []byte("fake-exe"), 0o755); err != nil {
		t.Fatalf("write exe: %v", err)
	}

	service := probeTestService(home)
	service.Environ = func() []string {
		return []string{"PATH=" + prefixBin}
	}
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	spec := ProviderSpec{
		Provider:       "opencode",
		AdapterCommand: []string{"opencode", "acp"},
		Install: InstallerSpec{
			Kind: InstallerKindManagedNPMPackage,
			ManagedNPM: &ManagedNPMPackageInstallerSpec{
				PackageName: "opencode-ai",
				BinaryName:  "opencode",
			},
		},
	}

	resolved := service.resolveManagedNPMAdapterCommand(spec)
	if len(resolved.AdapterCommand) < 2 {
		t.Fatalf("AdapterCommand len = %d, want >= 2", len(resolved.AdapterCommand))
	}
	if resolved.AdapterCommand[0] != exePath {
		t.Fatalf("AdapterCommand[0] = %q, want %q", resolved.AdapterCommand[0], exePath)
	}
	if resolved.AdapterCommand[1] != "acp" {
		t.Fatalf("AdapterCommand[1] = %q, want acp", resolved.AdapterCommand[1])
	}
}

func TestResolveManagedNPMAdapterCommandPreservesCommandWhenExeNotFound(t *testing.T) {
	home := t.TempDir()
	prefixBin := filepath.Join(home, ".local", "bin")

	service := probeTestService(home)
	service.Environ = func() []string {
		return []string{"PATH=" + prefixBin}
	}

	spec := ProviderSpec{
		Provider:       "opencode",
		AdapterCommand: []string{"opencode", "acp"},
		Install: InstallerSpec{
			Kind: InstallerKindManagedNPMPackage,
			ManagedNPM: &ManagedNPMPackageInstallerSpec{
				PackageName: "opencode-ai",
				BinaryName:  "opencode",
			},
		},
	}

	resolved := service.resolveManagedNPMAdapterCommand(spec)
	if resolved.AdapterCommand[0] != "opencode" {
		t.Fatalf("AdapterCommand[0] = %q, want opencode (unchanged)", resolved.AdapterCommand[0])
	}
}

func TestRunManagedNPMPackageInstallerPopulatesArgs(t *testing.T) {
	home := t.TempDir()
	runtimeRoot := fakeManagedRuntimeRoot(t)
	managedNPM := filepath.Join(runtimeRoot, "node", "bin", npmBinaryNameForTest())
	managedNode := filepath.Join(runtimeRoot, "node", "bin", nodeBinaryNameForTest())
	managedNodeBinDir := filepath.Dir(managedNode)
	setupNPMCLIJS(t, filepath.Dir(managedNPM))

	service := probeTestService(home)
	service.HTTPClient = agentNPMRegistryProbeHTTPClient(nil)
	service.Environ = func() []string {
		return []string{"PATH=/usr/bin:/bin", agentNPMRegistryEnv + "=https://registry.example.test"}
	}
	service.ManagedRuntime = staticManagedRuntimeResolver{
		runtime: managedruntime.ResolvedRuntime{
			Root:    runtimeRoot,
			Node:    managedNode,
			NPM:     managedNPM,
			BinDirs: []string{managedNodeBinDir},
			EnvOverrides: []string{
				"TUTTI_APP_RUNTIME_ROOT=" + runtimeRoot,
				"TUTTI_APP_NODE=" + managedNode,
				"TUTTI_APP_NPM=" + managedNPM,
				"PATH=" + managedNodeBinDir,
			},
		},
	}
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	var command InstallCommandInput
	service.InstallCommand = func(_ context.Context, input InstallCommandInput) (InstallCommandResult, error) {
		command = input
		return InstallCommandResult{ExitCode: 0, Stdout: "installed"}, nil
	}

	if _, err := service.runManagedNPMPackageInstaller(context.Background(), "tutti-agent", ManagedNPMPackageInstallerSpec{
		PackageName:     "@tutti-os/tutti-agent",
		BinaryName:      "tutti-agent",
		IncludeOptional: true,
	}, ""); err != nil {
		t.Fatalf("runManagedNPMPackageInstaller() error = %v", err)
	}
	if len(command.Args) == 0 {
		t.Fatalf("Args is empty, want populated argv")
	}

	if runtime.GOOS == "windows" {
		if command.Args[0] != managedNode {
			t.Fatalf("Args[0] = %q, want %q (node.exe)", command.Args[0], managedNode)
		}
		if !strings.Contains(command.Args[1], "npm-cli.js") {
			t.Fatalf("Args[1] = %q, want npm-cli.js path", command.Args[1])
		}
		if command.Args[2] != "install" {
			t.Fatalf("Args[2] = %q, want install", command.Args[2])
		}
		if command.Args[3] != "-g" {
			t.Fatalf("Args[3] = %q, want -g", command.Args[3])
		}
	} else {
		if command.Args[0] != managedNPM {
			t.Fatalf("Args[0] = %q, want %q (npm)", command.Args[0], managedNPM)
		}
		if command.Args[1] != "install" {
			t.Fatalf("Args[1] = %q, want install", command.Args[1])
		}
		if command.Args[2] != "-g" {
			t.Fatalf("Args[2] = %q, want -g", command.Args[2])
		}
	}
	if command.Command == "" {
		t.Fatalf("Command is empty, want display string")
	}
}

func TestResolveNPMCLIJSLayoutOne(t *testing.T) {
	tmp := t.TempDir()
	npmDir := filepath.Join(tmp, "nodejs")
	npmPath := filepath.Join(npmDir, "npm.cmd")
	cliPath := filepath.Join(npmDir, "node_modules", "npm", "bin", "npm-cli.js")
	if err := os.MkdirAll(filepath.Dir(cliPath), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(cliPath, []byte("// npm-cli.js\n"), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	resolved, err := resolveNPMCLIJS(npmPath)
	if err != nil {
		t.Fatalf("resolveNPMCLIJS() error = %v", err)
	}
	if resolved != cliPath {
		t.Fatalf("resolveNPMCLIJS() = %q, want %q", resolved, cliPath)
	}
}

func TestResolveNPMCLIJSLayoutTwo(t *testing.T) {
	tmp := t.TempDir()
	prefix := filepath.Join(tmp, "nvm", "versions", "node", "v24.12.0")
	binDir := filepath.Join(prefix, "bin")
	npmPath := filepath.Join(binDir, "npm.cmd")
	cliPath := filepath.Join(prefix, "lib", "node_modules", "npm", "bin", "npm-cli.js")
	if err := os.MkdirAll(filepath.Dir(npmPath), 0o755); err != nil {
		t.Fatalf("mkdir bin: %v", err)
	}
	if err := os.MkdirAll(filepath.Dir(cliPath), 0o755); err != nil {
		t.Fatalf("mkdir lib: %v", err)
	}
	if err := os.WriteFile(cliPath, []byte("// npm-cli.js\n"), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	resolved, err := resolveNPMCLIJS(npmPath)
	if err != nil {
		t.Fatalf("resolveNPMCLIJS() error = %v", err)
	}
	if resolved != filepath.Clean(cliPath) {
		t.Fatalf("resolveNPMCLIJS() = %q, want %q", resolved, filepath.Clean(cliPath))
	}
}

func TestResolveNPMCLIJSMissingCLI(t *testing.T) {
	tmp := t.TempDir()
	npmDir := filepath.Join(tmp, "nodejs")
	npmPath := filepath.Join(npmDir, "npm.cmd")
	if _, err := resolveNPMCLIJS(npmPath); err == nil {
		t.Fatalf("resolveNPMCLIJS() expected error for missing npm-cli.js")
	}
}

func TestRunArgvInstallCommandRejectsBatchFileOnWindows(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific batch file rejection test")
	}
	result, err := runArgvInstallCommand(context.Background(), InstallCommandInput{
		Args: []string{`C:\tools\npm.cmd`, "install", "-g"},
	})
	if err != nil {
		t.Fatalf("runArgvInstallCommand() error = %v", err)
	}
	if result.ExitCode == 0 {
		t.Fatalf("ExitCode = %d, want non-zero for batch file rejection", result.ExitCode)
	}
	if !strings.Contains(result.Stderr, "batch file") &&
		!strings.Contains(result.Stderr, "cannot be executed directly") {
		t.Fatalf("Stderr = %q, want batch file rejection message", result.Stderr)
	}
}

func TestRunDefaultInstallCommandUsesNodeForNPMOnWindows(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific node+npm-cli.js test")
	}
	nodeExe, err := exec.LookPath("node.exe")
	if err != nil {
		t.Skipf("node.exe not found on PATH: %v", err)
	}

	tmp := t.TempDir()
	spacedDir := filepath.Join(tmp, "Program Files", "nodejs")
	if err := os.MkdirAll(spacedDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	cliPath := filepath.Join(spacedDir, "node_modules", "npm", "bin", "npm-cli.js")
	if err := os.MkdirAll(filepath.Dir(cliPath), 0o755); err != nil {
		t.Fatalf("mkdir cli: %v", err)
	}
	outputPath := filepath.Join(tmp, "args-output.json")
	// npm-cli.js shim: serialize process.argv.slice(2) to a file
	shim := fmt.Sprintf(
		`var fs=require("fs");fs.writeFileSync(%s,JSON.stringify(process.argv.slice(2)));`,
		quoteJSONString(outputPath),
	)
	if err := os.WriteFile(cliPath, []byte(shim), 0o644); err != nil {
		t.Fatalf("write shim: %v", err)
	}

	installPrefix := filepath.Join(tmp, "spaced & prefix")
	args := []string{
		nodeExe,
		cliPath,
		"install",
		"-g",
		"--prefix", installPrefix,
		"@tutti-os/tutti-agent",
		"--include=optional",
		"--extra=left&right(%test%!)",
	}

	result, err := runDefaultInstallCommand(context.Background(), InstallCommandInput{
		Args: args,
	})
	if err != nil {
		t.Fatalf("runDefaultInstallCommand() error = %v", err)
	}
	if result.ExitCode != 0 {
		t.Fatalf("ExitCode = %d, want 0; stderr=%q stdout=%q", result.ExitCode, result.Stderr, result.Stdout)
	}

	data, err := os.ReadFile(outputPath)
	if err != nil {
		t.Fatalf("read args output: %v", err)
	}
	var parsed []string
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("parse args JSON: %v (data=%q)", err, string(data))
	}

	expected := args[2:]
	if len(parsed) != len(expected) {
		t.Fatalf("len(args) = %d, want %d; got=%#v want=%#v", len(parsed), len(expected), parsed, expected)
	}
	for i, arg := range expected {
		if parsed[i] != arg {
			t.Errorf("args[%d] = %q, want %q", i, parsed[i], arg)
		}
	}
}

func TestRunDefaultInstallCommandArgsExecutesDirectlyOnUnix(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix-specific direct execution test")
	}

	result, err := runDefaultInstallCommand(context.Background(), InstallCommandInput{
		Args: []string{"echo", "direct-argv-ok"},
	})
	if err != nil {
		t.Fatalf("runDefaultInstallCommand() error = %v", err)
	}
	if result.ExitCode != 0 {
		t.Fatalf("ExitCode = %d, want 0; stderr=%q", result.ExitCode, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "direct-argv-ok") {
		t.Fatalf("Stdout = %q, want direct-argv-ok", result.Stdout)
	}
}

func setupNPMCLIJS(t *testing.T, npmDir string) {
	t.Helper()
	cliPath := filepath.Join(npmDir, "node_modules", "npm", "bin", "npm-cli.js")
	if err := os.MkdirAll(filepath.Dir(cliPath), 0o755); err != nil {
		t.Fatalf("mkdir npm-cli.js: %v", err)
	}
	if err := os.WriteFile(cliPath, []byte("// npm-cli.js\n"), 0o644); err != nil {
		t.Fatalf("write npm-cli.js: %v", err)
	}
}

type nodeStaticOnlyResolver struct {
	runtime          managedruntime.ResolvedRuntime
	baselineCalled   *bool
	nodeStaticCalled *bool
}

func (r nodeStaticOnlyResolver) Resolve(context.Context) (managedruntime.ResolvedRuntime, error) {
	if r.baselineCalled != nil {
		*r.baselineCalled = true
	}
	return managedruntime.ResolvedRuntime{}, errors.New("baseline not available on Windows Node-only package")
}

func (r nodeStaticOnlyResolver) ResolveProfile(_ context.Context, profile string) (managedruntime.ResolvedRuntime, error) {
	if r.nodeStaticCalled != nil {
		*r.nodeStaticCalled = true
	}
	if profile == managedruntime.NodeStaticProfile {
		return r.runtime, nil
	}
	return managedruntime.ResolvedRuntime{}, fmt.Errorf("unsupported profile %q", profile)
}

func TestRunExternalAgentRegistryNPMInstallerUsesNodeStaticProfile(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific node-static profile test")
	}
	nodeExe, err := exec.LookPath("node.exe")
	if err != nil {
		t.Skipf("node.exe not found on PATH: %v", err)
	}

	tmp := t.TempDir()
	spacedNPMDir := filepath.Join(tmp, "spaced npm", "bin")
	if err := os.MkdirAll(spacedNPMDir, 0o755); err != nil {
		t.Fatalf("mkdir npm dir: %v", err)
	}
	npmPath := filepath.Join(spacedNPMDir, "npm.cmd")
	if err := os.WriteFile(npmPath, []byte("@echo off\r\nexit /b 0\r\n"), 0o644); err != nil {
		t.Fatalf("write npm shim: %v", err)
	}

	cliDir := filepath.Join(spacedNPMDir, "node_modules", "npm", "bin")
	if err := os.MkdirAll(cliDir, 0o755); err != nil {
		t.Fatalf("mkdir cli dir: %v", err)
	}
	cliPath := filepath.Join(cliDir, "npm-cli.js")
	outputPath := filepath.Join(tmp, "args-output.json")
	shim := fmt.Sprintf(
		`var fs=require("fs");fs.writeFileSync(%s,JSON.stringify(process.argv.slice(2)));`,
		quoteJSONString(outputPath),
	)
	if err := os.WriteFile(cliPath, []byte(shim), 0o644); err != nil {
		t.Fatalf("write npm-cli.js shim: %v", err)
	}

	prefixDir := filepath.Join(tmp, "spaced & prefix")
	if err := os.MkdirAll(prefixDir, 0o755); err != nil {
		t.Fatalf("mkdir prefix dir: %v", err)
	}

	var baselineCalled, nodeStaticCalled bool
	service := Service{
		ManagedRuntime: nodeStaticOnlyResolver{
			runtime: managedruntime.ResolvedRuntime{
				Root:         tmp,
				Node:         nodeExe,
				NPM:          npmPath,
				BinDirs:      []string{spacedNPMDir},
				EnvOverrides: []string{"PATH=" + spacedNPMDir + string(os.PathListSeparator) + os.Getenv("PATH")},
			},
			baselineCalled:   &baselineCalled,
			nodeStaticCalled: &nodeStaticCalled,
		},
		HTTPClient: agentNPMRegistryProbeHTTPClient(nil),
		Environ:    func() []string { return os.Environ() },
		HomeDir:    os.UserHomeDir,
		LookPath:   exec.LookPath,
	}

	result, err := service.runExternalAgentRegistryNPMInstaller(context.Background(), "test-agent", InstallerSpec{
		Kind: InstallerKindExternalAgentRegistryNPM,
		RegistryNPM: &ExternalAgentRegistryNPMInstallerSpec{
			AgentID:   "test-agent",
			Package:   "test-pkg@1.0.0",
			PrefixDir: prefixDir,
		},
	})
	if err != nil {
		t.Fatalf("runExternalAgentRegistryNPMInstaller() error = %v", err)
	}
	if result.ExitCode != 0 {
		t.Fatalf("install exitCode=%d, want 0; stdout=%s stderr=%s", result.ExitCode, result.Stdout, result.Stderr)
	}

	if baselineCalled {
		t.Error("baseline Resolve was called; want Node-static profile only")
	}
	if !nodeStaticCalled {
		t.Error("Node-static ResolveProfile was not called; want Node-only resolution")
	}

	data, err := os.ReadFile(outputPath)
	if err != nil {
		t.Fatalf("read args output: %v", err)
	}
	var parsed []string
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("parse args JSON: %v (data=%q)", err, string(data))
	}
	if len(parsed) < 4 {
		t.Fatalf("len(args) = %d, want >= 4; got=%#v", len(parsed), parsed)
	}
	wantPackage := boundedNPMPackageSpec("test-pkg@1.0.0")
	if parsed[0] != "--prefix" || parsed[1] != prefixDir || parsed[2] != "install" || parsed[3] != wantPackage {
		t.Fatalf("unexpected npm args: %#v (want pkg=%q)", parsed, wantPackage)
	}
}

func TestInstalledNPMPackageBinJSRejectsEscapingPath(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "safe-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	manifest := `{"name": "safe-pkg", "bin": "../escape/bin.js"}`
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	_, err := service.installedNPMPackageBinJS(pkgDir, "safe-pkg")
	if !errors.Is(err, errBinInvalid) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinInvalid", err)
	}
}

func TestInstalledNPMPackageBinJSRejectsDeepEscape(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "safe-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	manifest := `{"name": "safe-pkg", "bin": "../../outside/bin.js"}`
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	_, err := service.installedNPMPackageBinJS(pkgDir, "safe-pkg")
	if !errors.Is(err, errBinInvalid) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinInvalid", err)
	}
}

func TestInstalledNPMPackageBinJSNotInstalled(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "safe-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	manifest := `{"name": "safe-pkg", "version": "1.0.0"}`
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	_, err := service.installedNPMPackageBinJS(pkgDir, "safe-pkg")
	if !errors.Is(err, errBinNotInstalled) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinNotInstalled", err)
	}
}

func TestInstalledNPMPackageBinJSResolvesManifestBin(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "safe-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	binPath := filepath.Join(pkgDir, "dist", "cli.js")
	if err := os.MkdirAll(filepath.Dir(binPath), 0o755); err != nil {
		t.Fatalf("mkdir bin dir: %v", err)
	}
	if err := os.WriteFile(binPath, []byte("// cli.js\n"), 0o644); err != nil {
		t.Fatalf("write bin: %v", err)
	}
	manifest := fmt.Sprintf(`{"name": "safe-pkg", "bin": %s}`, quoteJSONString("dist/cli.js"))
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	got, err := service.installedNPMPackageBinJS(pkgDir, "safe-pkg")
	if err != nil {
		t.Fatalf("installedNPMPackageBinJS() error = %v", err)
	}
	if got != binPath {
		t.Fatalf("installedNPMPackageBinJS() = %q, want %q", got, binPath)
	}
}

func TestInstalledNPMPackageBinJSRejectsMultiBinWithoutDefault(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "multi-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	manifest := `{"name": "multi-pkg", "bin": {"other-a": "a.js", "other-b": "b.js"}}`
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	_, err := service.installedNPMPackageBinJS(pkgDir, "multi-pkg")
	if !errors.Is(err, errBinInvalid) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinInvalid", err)
	}
}

func TestInstalledNPMPackageBinJSRejectsMalformedManifest(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "bad-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte("{not json"), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	_, err := service.installedNPMPackageBinJS(pkgDir, "bad-pkg")
	if !errors.Is(err, errBinInvalid) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinInvalid", err)
	}
}

func TestInstalledNPMPackageBinJSRejectsMismatchedName(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "wrong-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	manifest := `{"name": "other-pkg", "bin": "cli.js"}`
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	_, err := service.installedNPMPackageBinJS(pkgDir, "wrong-pkg")
	if !errors.Is(err, errBinInvalid) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinInvalid", err)
	}
}

func TestResolveExternalRegistryNPMWindowsCommandRejectsInvalidBin(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific external registry command rejection test")
	}
	tmp := t.TempDir()
	prefixDir := filepath.Join(tmp, "prefix")
	pkgDir := filepath.Join(tmp, "packages", "bad-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(`{"name": "bad-pkg", "bin": "../escape/bin.js"}`), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{}
	got := service.resolveExternalRegistryNPMWindowsCommand(
		managedruntime.ResolvedRuntime{Node: "node.exe", NPM: "npm.cmd"},
		prefixDir, pkgDir, "bad-pkg",
		externalagentregistry.NPMDistribution{Package: "bad-pkg@1.0.0"},
	)
	if got != nil {
		t.Fatalf("resolveExternalRegistryNPMWindowsCommand() = %#v, want nil (rejection)", got)
	}
}

func TestRunClaudeAgentACPPatchArgsOnWindowsWithSpaces(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific Claude ACP patch argv test")
	}
	nodeExe, err := exec.LookPath("node.exe")
	if err != nil {
		t.Skipf("node.exe not found on PATH: %v", err)
	}

	tmp := t.TempDir()
	distDir := filepath.Join(tmp, "spaced & pkg", "dist")
	if err := os.MkdirAll(distDir, 0o755); err != nil {
		t.Fatalf("mkdir dist dir: %v", err)
	}
	distPath := filepath.Join(distDir, "acp-agent.js")
	if err := os.WriteFile(distPath, []byte("// placeholder\n"), 0o644); err != nil {
		t.Fatalf("write dist: %v", err)
	}

	markerPath := filepath.Join(tmp, "patch-marker.txt")
	replacementScript := fmt.Sprintf(
		`import{writeFileSync}from"fs";writeFileSync(%s,JSON.stringify(process.argv.slice(2)));`,
		quoteJSONString(markerPath),
	)
	savedScript := claudeAgentACPPatchScript
	claudeAgentACPPatchScript = []byte(replacementScript)
	t.Cleanup(func() { claudeAgentACPPatchScript = savedScript })

	service := Service{
		ManagedRuntime: nodeStaticOnlyResolver{
			runtime: managedruntime.ResolvedRuntime{
				Node:         nodeExe,
				EnvOverrides: []string{"PATH=" + filepath.Dir(nodeExe) + string(os.PathListSeparator) + os.Getenv("PATH")},
			},
		},
		Environ: func() []string { return os.Environ() },
		HomeDir: os.UserHomeDir,
	}
	result, err := service.runClaudeAgentACPPatch(context.Background(), InstallerSpec{
		RegistryNPM: &ExternalAgentRegistryNPMInstallerSpec{
			PackageDir: filepath.Join(tmp, "spaced & pkg"),
			Env:        map[string]string{},
		},
	})
	if err != nil {
		t.Fatalf("runClaudeAgentACPPatch() error = %v", err)
	}
	if result.ExitCode != 0 {
		t.Fatalf("ExitCode = %d, want 0; stdout=%s stderr=%s", result.ExitCode, result.Stdout, result.Stderr)
	}

	data, err := os.ReadFile(markerPath)
	if err != nil {
		t.Fatalf("read marker: %v", err)
	}
	var parsed []string
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("parse marker JSON: %v (data=%q)", err, string(data))
	}
	if len(parsed) < 2 || parsed[0] != "--dist" || parsed[1] != distPath {
		t.Fatalf("argv = %#v, want [--dist, %q]", parsed, distPath)
	}
}

func TestInstalledNPMPackageBinJSRejectsSymlinkEscape(t *testing.T) {
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "safe-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	outsidePath := filepath.Join(tmp, "outside", "real-bin.js")
	if err := os.MkdirAll(filepath.Dir(outsidePath), 0o755); err != nil {
		t.Fatalf("mkdir outside dir: %v", err)
	}
	if err := os.WriteFile(outsidePath, []byte("// real bin\n"), 0o644); err != nil {
		t.Fatalf("write outside bin: %v", err)
	}
	linkPath := filepath.Join(pkgDir, "linked-bin.js")
	if err := os.Symlink(outsidePath, linkPath); err != nil {
		t.Skipf("symlink creation not available: %v", err)
	}
	manifest := `{"name": "safe-pkg", "bin": "linked-bin.js"}`
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{IsExecutableFile: func(string) bool { return true }}
	_, err := service.installedNPMPackageBinJS(pkgDir, "safe-pkg")
	if !errors.Is(err, errBinInvalid) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinInvalid", err)
	}
}

func TestInstalledNPMPackageBinJSRejectsJunctionEscape(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific junction escape test")
	}
	tmp := t.TempDir()
	pkgDir := filepath.Join(tmp, "packages", "safe-pkg")
	if err := os.MkdirAll(pkgDir, 0o755); err != nil {
		t.Fatalf("mkdir pkg dir: %v", err)
	}
	outsideDir := filepath.Join(tmp, "outside")
	if err := os.MkdirAll(outsideDir, 0o755); err != nil {
		t.Fatalf("mkdir outside dir: %v", err)
	}
	outsideBin := filepath.Join(outsideDir, "real-bin.js")
	if err := os.WriteFile(outsideBin, []byte("// real bin\n"), 0o644); err != nil {
		t.Fatalf("write outside bin: %v", err)
	}
	linkPoint := filepath.Join(pkgDir, "linked")
	cmd := exec.Command("cmd.exe", "/C", "mklink", "/J", linkPoint, outsideDir)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Skipf("junction creation unavailable: %v (out=%s)", err, string(out))
	}
	manifest := `{"name": "safe-pkg", "bin": "linked/real-bin.js"}`
	if err := os.WriteFile(filepath.Join(pkgDir, "package.json"), []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}
	service := Service{}
	_, err := service.installedNPMPackageBinJS(pkgDir, "safe-pkg")
	if !errors.Is(err, errBinInvalid) {
		t.Fatalf("installedNPMPackageBinJS() err = %v, want errBinInvalid", err)
	}
	got := service.resolveExternalRegistryNPMWindowsCommand(
		managedruntime.ResolvedRuntime{Node: "node.exe", NPM: "npm.cmd"},
		filepath.Join(tmp, "prefix"), pkgDir, "safe-pkg",
		externalagentregistry.NPMDistribution{Package: "safe-pkg@1.0.0"},
	)
	if got != nil {
		t.Fatalf("resolveExternalRegistryNPMWindowsCommand() = %#v, want nil (rejection)", got)
	}
}

func TestRunManagedNPMPackageInstallPrefixOnWindowsEqualsInstallBinDir(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific npm prefix layout test")
	}
	home := t.TempDir()
	runtimeRoot := fakeManagedRuntimeRoot(t)
	managedNPM := filepath.Join(runtimeRoot, "node", "bin", npmBinaryNameForTest())
	managedNode := filepath.Join(runtimeRoot, "node", "bin", nodeBinaryNameForTest())
	managedNodeBinDir := filepath.Dir(managedNode)
	setupNPMCLIJS(t, filepath.Dir(managedNPM))

	service := probeTestService(home)
	service.HTTPClient = agentNPMRegistryProbeHTTPClient(nil)
	service.Environ = func() []string {
		return []string{"PATH=/usr/bin:/bin", agentNPMRegistryEnv + "=https://registry.example.test"}
	}
	service.ManagedRuntime = staticManagedRuntimeResolver{
		runtime: managedruntime.ResolvedRuntime{
			Root:    runtimeRoot,
			Node:    managedNode,
			NPM:     managedNPM,
			BinDirs: []string{managedNodeBinDir},
			EnvOverrides: []string{
				"TUTTI_APP_RUNTIME_ROOT=" + runtimeRoot,
				"TUTTI_APP_NODE=" + managedNode,
				"TUTTI_APP_NPM=" + managedNPM,
				"PATH=" + managedNodeBinDir + string(os.PathListSeparator) + "/usr/bin" + string(os.PathListSeparator) + "/bin",
			},
		},
	}
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	var capturedPrefix string
	service.InstallCommand = func(_ context.Context, input InstallCommandInput) (InstallCommandResult, error) {
		args := input.Args
		for i, arg := range args {
			if arg == "--prefix" && i+1 < len(args) {
				capturedPrefix = args[i+1]
			}
		}
		if capturedPrefix != "" {
			launcherPath := filepath.Join(capturedPrefix, "tutti-agent.cmd")
			if err := os.WriteFile(launcherPath, []byte("@echo off\r\nexit /b 0\r\n"), 0o755); err != nil {
				return InstallCommandResult{}, err
			}
			plainBin := filepath.Join(capturedPrefix, "tutti-agent")
			if err := os.WriteFile(plainBin, []byte("@echo off\r\nexit /b 0\r\n"), 0o755); err != nil {
				return InstallCommandResult{}, err
			}
		}
		return InstallCommandResult{ExitCode: 0, Stdout: "installed"}, nil
	}

	_, err := service.runManagedNPMPackageInstaller(context.Background(), "tutti-agent", ManagedNPMPackageInstallerSpec{
		PackageName:     "@tutti-os/tutti-agent",
		BinaryName:      "tutti-agent",
		IncludeOptional: true,
	}, "")
	if err != nil {
		t.Fatalf("runManagedNPMPackageInstaller() error = %v", err)
	}

	installBinDir := filepath.Join(home, ".local", "bin")
	if capturedPrefix != installBinDir {
		t.Fatalf("prefix = %q, want %q (installBinDir on Windows)", capturedPrefix, installBinDir)
	}

	resolver := service.commandResolver()
	found := resolveBinaryWithResolver(resolver, []string{"tutti-agent"}, nil)
	if found == "" {
		t.Fatalf("resolveBinaryWithResolver did not find tutti-agent after install; installBinDir=%s", installBinDir)
	}
	if found != filepath.Join(installBinDir, "tutti-agent") {
		t.Fatalf("resolved binary = %q, want %q", found, filepath.Join(installBinDir, "tutti-agent"))
	}
}

func TestRunManagedNPMPackageInstallPrefixOnUnixUsesParentOfInstallBinDir(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix-specific npm prefix layout test")
	}
	home := t.TempDir()
	runtimeRoot := fakeManagedRuntimeRoot(t)
	managedNPM := filepath.Join(runtimeRoot, "node", "bin", npmBinaryNameForTest())
	managedNode := filepath.Join(runtimeRoot, "node", "bin", nodeBinaryNameForTest())
	managedNodeBinDir := filepath.Dir(managedNode)
	setupNPMCLIJS(t, filepath.Dir(managedNPM))

	service := probeTestService(home)
	service.HTTPClient = agentNPMRegistryProbeHTTPClient(nil)
	service.Environ = func() []string {
		return []string{"PATH=/usr/bin:/bin", agentNPMRegistryEnv + "=https://registry.example.test"}
	}
	service.ManagedRuntime = staticManagedRuntimeResolver{
		runtime: managedruntime.ResolvedRuntime{
			Root:    runtimeRoot,
			Node:    managedNode,
			NPM:     managedNPM,
			BinDirs: []string{managedNodeBinDir},
			EnvOverrides: []string{
				"TUTTI_APP_RUNTIME_ROOT=" + runtimeRoot,
				"TUTTI_APP_NODE=" + managedNode,
				"TUTTI_APP_NPM=" + managedNPM,
				"PATH=" + managedNodeBinDir + string(os.PathListSeparator) + "/usr/bin" + string(os.PathListSeparator) + "/bin",
			},
		},
	}
	service.IsExecutableFile = isTestExecutableUnderHome(home)

	var capturedPrefix string
	service.InstallCommand = func(_ context.Context, input InstallCommandInput) (InstallCommandResult, error) {
		args := input.Args
		for i, arg := range args {
			if arg == "--prefix" && i+1 < len(args) {
				capturedPrefix = args[i+1]
			}
		}
		if capturedPrefix != "" {
			launcherPath := filepath.Join(capturedPrefix, "bin", "tutti-agent")
			if err := os.MkdirAll(filepath.Dir(launcherPath), 0o755); err != nil {
				return InstallCommandResult{}, err
			}
			if err := os.WriteFile(launcherPath, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
				return InstallCommandResult{}, err
			}
		}
		return InstallCommandResult{ExitCode: 0, Stdout: "installed"}, nil
	}

	_, err := service.runManagedNPMPackageInstaller(context.Background(), "tutti-agent", ManagedNPMPackageInstallerSpec{
		PackageName:     "@tutti-os/tutti-agent",
		BinaryName:      "tutti-agent",
		IncludeOptional: true,
	}, "")
	if err != nil {
		t.Fatalf("runManagedNPMPackageInstaller() error = %v", err)
	}

	wantPrefix := filepath.Join(home, ".local")
	if capturedPrefix != wantPrefix {
		t.Fatalf("prefix = %q, want %q (parent of installBinDir on Unix)", capturedPrefix, wantPrefix)
	}

	installBinDir := filepath.Join(home, ".local", "bin")
	resolver := service.commandResolver()
	found := resolveBinaryWithResolver(resolver, []string{"tutti-agent"}, nil)
	if found == "" {
		t.Fatalf("resolveBinaryWithResolver did not find tutti-agent after install; installBinDir=%s", installBinDir)
	}
	if found != filepath.Join(installBinDir, "tutti-agent") {
		t.Fatalf("resolved binary = %q, want %q", found, filepath.Join(installBinDir, "tutti-agent"))
	}
}
