package agentstatus

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"

	"github.com/tutti-os/tutti/packages/agent/daemon/runtimecmd"
	"github.com/tutti-os/tutti/services/tuttid/biz/agentprovider"
	managedruntime "github.com/tutti-os/tutti/services/tuttid/service/managedruntime"
)

// displayNPMRegistry returns a registry URL safe to surface in status and logs.
// A custom registry override (agentNPMRegistryEnv) can embed credentials as
// userinfo (https://user:token@host); strip them so they never reach the wizard
// UI, telemetry, or log lines. The raw URL is still used for the npm env.
func displayNPMRegistry(registry string) string {
	trimmed := strings.TrimSpace(registry)
	parsed, err := url.Parse(trimmed)
	if err != nil || parsed.User == nil {
		return trimmed
	}
	parsed.User = nil
	return parsed.String()
}

func (s Service) runCodexCLILatestInstaller(
	ctx context.Context,
	spec InstallerSpec,
	existingCLIPath string,
) (InstallCommandResult, error) {
	if spec.CodexCLI == nil {
		return InstallCommandResult{ExitCode: 1, Stderr: "codex CLI latest installer config is required"}, nil
	}
	return s.runManagedNPMPackageInstaller(ctx, agentprovider.Codex, ManagedNPMPackageInstallerSpec{
		PackageName:     "@openai/codex",
		BinaryName:      "codex",
		IncludeOptional: true,
	}, existingCLIPath)
}

func (s Service) runManagedNPMPackageInstaller(
	ctx context.Context,
	provider string,
	spec ManagedNPMPackageInstallerSpec,
	existingCLIPath string,
) (InstallCommandResult, error) {
	packageName := strings.TrimSpace(spec.PackageName)
	binaryName := strings.TrimSpace(spec.BinaryName)
	if packageName == "" {
		return InstallCommandResult{ExitCode: 1, Stderr: "managed npm package name is required"}, nil
	}
	if binaryName == "" {
		return InstallCommandResult{ExitCode: 1, Stderr: "managed npm package binary name is required"}, nil
	}
	resolver := s.commandResolver()
	npmPath, nodeTarget, baseEnv, err := s.resolveManagedNPMInstallerNodeRuntime(ctx, resolver)
	if err != nil {
		return InstallCommandResult{ExitCode: 1, Stderr: err.Error()}, nil
	}
	// A bare `npm install -g` lands the launcher in whichever npm's global prefix
	// runs the install. In the desktop app that npm can be the bundled app-runtime
	// node, whose prefix (~/.tutti/app-runtimes/.../node) is NOT on the binary
	// resolver's search path — so the install succeeds but `codex` is never found
	// and the wizard reports "provider CLI is still unavailable after install".
	// Pin the global prefix to the same stable, always-searched dir the
	// release-binary installer uses (selectInstallDir -> ~/.local/bin) so the
	// launcher stays discoverable regardless of which npm executes the install.
	installBinDir := strings.TrimSpace(spec.InstallDir)
	if installBinDir == "" {
		installBinDir, err = s.selectInstallDir()
		if err != nil {
			return InstallCommandResult{ExitCode: 1, Stderr: err.Error()}, nil
		}
	}
	installPrefix := filepath.Dir(installBinDir)
	if runtime.GOOS == "windows" {
		installPrefix = installBinDir
	}
	step := "install"
	// Repair-in-place: when an existing @openai/codex launcher is already on
	// PATH but its platform subpackage is missing (or it is outdated), installing
	// a SECOND copy in ~/.local does not help — the resolver prefers the
	// version-manager dir that already holds the broken copy, so the new copy in
	// ~/.local/bin is never selected and the wizard loops on "platform package
	// incomplete". Derive the npm global prefix that owns the existing package and
	// reinstall there with --include=optional so the missing platform binary is
	// restored in place. Falls back to the ~/.local install above when no existing
	// install can be located.
	if repairPrefix, ok := managedNPMRepairInstallPrefix(existingCLIPath, packageName); ok {
		installPrefix = repairPrefix
		step = "repair"
		slog.Info(
			"agent provider managed npm install repairing in place",
			"provider", provider,
			"package", packageName,
			"binary", binaryName,
			"existingCLIPath", existingCLIPath,
			"prefix", installPrefix,
		)
	}
	commandArgs := []string{npmPath, "install", "-g", "--prefix", installPrefix, managedNPMPackageSpec(spec)}
	if spec.IncludeOptional {
		commandArgs = append(commandArgs, "--include=optional")
	}
	command := joinShellCommand(commandArgs)
	if runtime.GOOS == "windows" {
		npmCLIPath, err := resolveNPMCLIJS(npmPath)
		if err != nil {
			return InstallCommandResult{ExitCode: 1, Stderr: err.Error()}, nil
		}
		npmArgs := commandArgs[1:]
		commandArgs = append([]string{nodeTarget, npmCLIPath}, npmArgs...)
	}
	// Pin a dedicated, tutti-owned npm cache instead of the user's global ~/.npm,
	// which on some machines holds root-owned files that make every user-mode npm
	// install fail with EACCES before any registry is hit.
	baseEnv = withAgentNPMCache(baseEnv, filepath.Join(installPrefix, agentNPMCacheDirName))
	registries := s.rankedAgentNPMRegistries(ctx, packageName)
	var result InstallCommandResult
	for i, registry := range registries {
		registryDisplay := displayNPMRegistry(registry)
		setActiveAction(ctx, provider, ActiveAction{
			ID:         ActionInstall,
			Status:     "running",
			Step:       step,
			Registry:   registryDisplay,
			NodeTarget: nodeTarget,
		})
		attemptCtx, cancel := context.WithTimeout(ctx, perRegistryInstallTimeout)
		result, err = s.installCommand(attemptCtx, InstallCommandInput{
			Command: command,
			Args:    slices.Clone(commandArgs),
			Env:     withAgentNPMRegistry(slices.Clone(baseEnv), registry),
			OnStdout: func(output string) {
				appendActiveActionStdout(ctx, provider, output)
			},
		})
		cancel()
		if err == nil && result.ExitCode == 0 {
			setActiveAction(ctx, provider, ActiveAction{
				ID:         ActionInstall,
				Status:     "running",
				Step:       "verify",
				Registry:   registryDisplay,
				NodeTarget: nodeTarget,
				Stdout:     result.Stdout,
			})
			return result, nil
		}
		if i < len(registries)-1 {
			slog.Warn(
				"agent provider managed npm install failed on registry, trying next",
				"provider", provider,
				"package", packageName,
				"registry", registryDisplay,
				"exitCode", result.ExitCode,
				"error", err,
			)
		}
	}
	return result, err
}

func (s Service) resolveManagedNPMInstallerNodeRuntime(
	ctx context.Context,
	resolver runtimecmd.Resolver,
) (string, string, []string, error) {
	appRuntime, err := s.resolveManagedNodeRuntime(ctx)
	if err != nil {
		if npmPath := strings.TrimSpace(resolveBinaryWithResolver(resolver, []string{npmBinaryName()}, nil)); npmPath != "" {
			nodeTarget := firstNonBlank(resolveBinaryWithResolver(resolver, []string{nodeBinaryName()}, nil), nodeBinaryName())
			return npmPath, nodeTarget, resolver.Env(nil), nil
		}
		return "", "", nil, fmt.Errorf("tutti managed Node runtime is unavailable and npm was not found on PATH: %w", err)
	}
	npmPath := strings.TrimSpace(appRuntime.NPM)
	if npmPath == "" {
		if fallbackNPM := strings.TrimSpace(resolveBinaryWithResolver(resolver, []string{npmBinaryName()}, nil)); fallbackNPM != "" {
			nodeTarget := firstNonBlank(resolveBinaryWithResolver(resolver, []string{nodeBinaryName()}, nil), nodeBinaryName())
			return fallbackNPM, nodeTarget, resolver.Env(nil), nil
		}
		return "", "", nil, fmt.Errorf("tutti managed Node runtime did not provide npm and npm was not found on PATH")
	}
	return npmPath, firstNonBlank(appRuntime.Node, nodeBinaryName()), managedruntime.ProcessEnv(appRuntime.EnvOverrides...), nil
}

func managedNPMPackageSpec(spec ManagedNPMPackageInstallerSpec) string {
	packageName := strings.TrimSpace(spec.PackageName)
	version := strings.TrimSpace(spec.PackageVersion)
	if version == "" {
		return packageName
	}
	return packageName + "@" + version
}

func managedNPMRepairInstallPrefix(existingCLIPath, packageName string) (string, bool) {
	existingCLIPath = strings.TrimSpace(existingCLIPath)
	if existingCLIPath == "" {
		return "", false
	}
	packageJSONPath := findAdapterPackageJSON(existingCLIPath, packageName)
	if packageJSONPath == "" {
		return "", false
	}
	prefix := npmGlobalPrefixFromPackageDir(filepath.Dir(packageJSONPath))
	if prefix == "" {
		return "", false
	}
	return prefix, true
}

func (s Service) resolveManagedNodeRuntime(ctx context.Context) (managedruntime.ResolvedRuntime, error) {
	resolver := s.managedRuntimeResolver()
	if managed, ok := resolver.(managedruntime.DefaultResolver); ok {
		root := strings.TrimSpace(managed.RuntimeRoot)
		if root == "" {
			root = managed.DefaultRoot()
		}
		if runtime, ok := resolvedExistingManagedNodeRuntime(root, s.Environ); ok {
			return runtime, nil
		}
	}
	if profileResolver, ok := resolver.(managedruntime.ProfileResolver); ok {
		return profileResolver.ResolveProfile(ctx, managedruntime.NodeStaticProfile)
	}
	return resolver.Resolve(ctx)
}

func nodeBinaryName() string {
	if runtime.GOOS == "windows" {
		return "node.exe"
	}
	return "node"
}

func npmBinaryName() string {
	if runtime.GOOS == "windows" {
		return "npm.cmd"
	}
	return "npm"
}

// resolveNPMCLIJS resolves the npm CLI JavaScript entry point relative to a
// Windows npm launcher (npm.cmd). On Windows, npm.cmd is a batch shim; to
// avoid cmd.exe quoting issues, callers should invoke the resolved CLI script
// through node.exe directly with structured argv.
//
// Layout 1 (official Windows Node distribution):
//
//	<npm-dir>/node_modules/npm/bin/npm-cli.js
//
// Layout 2 (version-manager / Unix-style global install):
//
//	<npm-dir>/../lib/node_modules/npm/bin/npm-cli.js
func resolveNPMCLIJS(npmPath string) (string, error) {
	npmPath = strings.TrimSpace(npmPath)
	if npmPath == "" {
		return "", errors.New("npm path is required to resolve CLI script")
	}
	npmDir := filepath.Dir(npmPath)

	candidates := []string{
		filepath.Join(npmDir, "node_modules", "npm", "bin", "npm-cli.js"),
		filepath.Join(npmDir, "..", "lib", "node_modules", "npm", "bin", "npm-cli.js"),
	}
	for _, candidate := range candidates {
		info, err := os.Stat(candidate)
		if err == nil && info.Mode().IsRegular() {
			return filepath.Clean(candidate), nil
		}
	}
	return "", fmt.Errorf("npm CLI script not found relative to %s (checked %s and %s)", npmPath, candidates[0], candidates[1])
}

func (s Service) resolveManagedNPMNativeExe(spec ManagedNPMPackageInstallerSpec, env []string) string {
	if runtime.GOOS != "windows" {
		return ""
	}
	packageName := strings.TrimSpace(spec.PackageName)
	binaryName := strings.TrimSpace(spec.BinaryName)
	if packageName == "" || binaryName == "" {
		return ""
	}
	for _, dir := range filepath.SplitList(managedruntime.EnvValue(env, "PATH")) {
		dir = filepath.Clean(dir)
		if strings.TrimSpace(dir) == "" {
			continue
		}
		candidate := filepath.Join(dir, "node_modules", packageName, "bin", binaryName+".exe")
		if s.validManagedNPMNativeExe(candidate, dir, packageName) {
			return candidate
		}
	}
	return ""
}

func (s Service) validManagedNPMNativeExe(candidate string, prefixDir string, packageName string) bool {
	prefixDir = filepath.Clean(prefixDir)
	candidate = filepath.Clean(candidate)

	packageDir := filepath.Join(prefixDir, "node_modules", packageName)
	packageDir = filepath.Clean(packageDir)

	rel, err := filepath.Rel(packageDir, candidate)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return false
	}

	info, err := os.Stat(candidate)
	if err != nil || !info.Mode().IsRegular() {
		return false
	}

	realPkgDir, pkgErr := filepath.EvalSymlinks(packageDir)
	if pkgErr != nil {
		return false
	}
	realCandidate, candErr := filepath.EvalSymlinks(candidate)
	if candErr != nil {
		return false
	}
	rel, err = filepath.Rel(realPkgDir, realCandidate)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return false
	}

	return true
}

func (s Service) resolveManagedNPMAdapterCommand(spec ProviderSpec) ProviderSpec {
	if len(spec.AdapterCommand) == 0 || spec.Install.ManagedNPM == nil {
		return spec
	}
	env := s.commandResolver().Env(spec.AdapterEnv)
	nativeExe := s.resolveManagedNPMNativeExe(*spec.Install.ManagedNPM, env)
	if nativeExe == "" {
		return spec
	}
	command := cloneStrings(spec.AdapterCommand)
	command[0] = nativeExe
	spec.AdapterCommand = command
	return spec
}
