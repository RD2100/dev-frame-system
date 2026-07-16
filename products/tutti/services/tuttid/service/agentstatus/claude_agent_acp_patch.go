package agentstatus

import (
	"context"
	_ "embed"
	"os"
	"path/filepath"

	managedruntime "github.com/tutti-os/tutti/services/tuttid/service/managedruntime"
)

// claudeAgentACPPatchScript is the idempotent codemod that teaches the
// claude-agent-acp bridge to advertise a `fast` config option backed by the
// Claude Agent SDK's `Settings.fastMode`. It is embedded so the installer can
// apply it self-contained, and is also runnable directly via
// `pnpm patch:claude-agent-acp`.
//
//go:embed assets/patch-claude-agent-acp.mjs
var claudeAgentACPPatchScript []byte

// runClaudeAgentACPPatch writes the embedded codemod to a temp file and runs it
// with node. Mirrors runOfficialScriptInstaller's temp-file pattern.
func (s Service) runClaudeAgentACPPatch(
	ctx context.Context,
	spec InstallerSpec,
) (InstallCommandResult, error) {
	scriptFile, err := os.CreateTemp("", "tutti-patch-claude-agent-acp-*.mjs")
	if err != nil {
		return InstallCommandResult{ExitCode: 1}, err
	}
	scriptPath := scriptFile.Name()
	defer func() {
		_ = os.Remove(scriptPath)
	}()
	if _, err := scriptFile.Write(claudeAgentACPPatchScript); err != nil {
		_ = scriptFile.Close()
		return InstallCommandResult{ExitCode: 1}, err
	}
	if err := scriptFile.Close(); err != nil {
		return InstallCommandResult{ExitCode: 1}, err
	}
	if spec.RegistryNPM != nil {
		appRuntime, err := s.resolveManagedNodeRuntime(ctx)
		if err != nil {
			return InstallCommandResult{ExitCode: 1}, err
		}
		distPath := filepath.Join(spec.RegistryNPM.PackageDir, "dist", "acp-agent.js")
		return s.installCommand(ctx, InstallCommandInput{
			Command: joinShellCommand([]string{appRuntime.Node, scriptPath, "--dist", distPath}),
			Args:    []string{appRuntime.Node, scriptPath, "--dist", distPath},
			Env:     managedruntime.ProcessEnv(append(appRuntime.EnvOverrides, envMapToList(spec.RegistryNPM.Env)...)...),
		})
	}
	return s.installCommand(ctx, InstallCommandInput{
		Command: joinShellCommand([]string{"node", scriptPath}),
		Args:    []string{"node", scriptPath},
		Env:     s.commandResolver().Env(nil),
	})
}

// applyInstallerPostStep runs the optional post-install step for a successful
// install. It is best-effort: a failure is surfaced in the returned result's
// Stderr but never downgrades the install's success (the bridge is installed;
// the patch only enables the orthogonal `fast` control).
func (s Service) applyInstallerPostStep(
	ctx context.Context,
	spec InstallerSpec,
	result InstallCommandResult,
) InstallCommandResult {
	if spec.PostInstall != InstallerPostStepPatchClaudeAgentACP {
		return result
	}
	patchResult, err := s.runClaudeAgentACPPatch(ctx, spec)
	if err == nil && patchResult.ExitCode == 0 {
		return result
	}
	detail := patchResult.Stderr
	if detail == "" {
		detail = patchResult.Stdout
	}
	if err != nil {
		detail = appendDetail(detail, err.Error())
	}
	result.Stderr = appendDetail(
		result.Stderr,
		"claude-agent-acp fast-mode patch did not apply: "+detail,
	)
	return result
}

func appendDetail(existing string, detail string) string {
	if existing == "" {
		return detail
	}
	if detail == "" {
		return existing
	}
	return existing + "\n" + detail
}
