package agentruntime

// Claude Code's ACP-family provider config (the `claude-agent-acp` bridge).
// The default Claude Code runtime is the SDK sidecar (claude_sdk_adapter.go);
// this ACP path is selected via TUTTI_CLAUDE_CODE_RUNTIME=acp.

import (
	"fmt"
	"os"
	"strings"
)

const claudeSystemPromptFileEnv = "TUTTI_CLAUDE_SYSTEM_PROMPT_FILE"

const claudePluginDirEnv = "TUTTI_CLAUDE_PLUGIN_DIR"

const claudeSDKMessageMethod = "_claude/sdkMessage"

const claudePlanModeInstructions = "You are in plan mode. Inspect files and gather context as needed, but do not edit files, run mutation commands, or make external changes. Produce a concrete implementation plan first. If the user gives feedback, refine the plan. Only after the user approves leaving plan mode may you implement changes."

const (
	sessionSpeedStandard = "standard"
	sessionSpeedFast     = "fast"

	claudeCodeACPFastOff = "off"
	claudeCodeACPFastOn  = "on"
)

var claudeCodeACPModelAliases = map[string]bool{
	"default":    true,
	"sonnet":     true,
	"opus":       true,
	"haiku":      true,
	"sonnet[1m]": true,
	"opusplan":   true,
}

// claudeCodeLegacyACPModelCandidates lists live ACP model values to try when a
// persisted alias (e.g. "opus") is not directly advertised. Order matters:
// claude-agent-acp 0.46+ exposes Opus as "opus[1m]"; 0.42.x folded Opus into
// "default" and rejected bare "opus".
func claudeCodeLegacyACPModelCandidates(model string) []string {
	switch strings.TrimSpace(model) {
	case "opus", "opusplan":
		return []string{"opus[1m]", "opus", "default"}
	default:
		return nil
	}
}

func claudeSystemPromptAppend(env []string) (string, error) {
	path := sessionEnvValue(env, claudeSystemPromptFileEnv)
	if strings.TrimSpace(path) == "" {
		return "", nil
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read claude system prompt: %w", err)
	}
	return string(content), nil
}

func claudePluginDir(env []string) (string, error) {
	path := sessionEnvValue(env, claudePluginDirEnv)
	if strings.TrimSpace(path) == "" {
		return "", nil
	}
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("stat claude plugin dir: %w", err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("claude plugin dir is not a directory: %s", path)
	}
	return path, nil
}

func claudeCodeACPModeID(mode string) string {
	if isClaudeCodePermissionModeID(mode) {
		return strings.TrimSpace(mode)
	}
	return ""
}

func claudeCodeACPCommands() []AgentSessionCommand {
	return []AgentSessionCommand{
		{Name: "review"},
		{Name: "compact"},
	}
}

func NewClaudeCodeAdapter(transport ProcessTransport) *standardACPAdapter {
	return NewClaudeCodeAdapterWithHostMetadata(transport, LegacyHostMetadata())
}

func NewClaudeCodeAdapterWithHostMetadata(transport ProcessTransport, host HostMetadata) *standardACPAdapter {
	return newClaudeCodeAdapterWithHostMetadata(transport, host, nil)
}

func newClaudeCodeAdapterWithHostMetadata(
	transport ProcessTransport,
	host HostMetadata,
	commandResolver ProviderCommandResolver,
) *standardACPAdapter {
	return &standardACPAdapter{
		config: standardACPConfig{
			provider:            ProviderClaudeCode,
			adapterName:         "claude-agent-acp",
			command:             []string{"claude-agent-acp"},
			defaultTitle:        "Claude Agent",
			defaultTitleAliases: []string{"Claude Code", ProviderClaudeCode},
			authRequiredMessage: "Claude Agent ACP requires authentication in the runtime VM; sign in to the local Claude Code agent so its credentials can be synced, then retry this session.",
			permissionModeID:    claudeCodeACPModeID,
			initializeParams:    func() map[string]any { return claudeACPInitializeParams(host) },
			failOnSetModeError:  true,
			env:                 func(session Session) []string { return claudeACPEnv(session, host) },
			commandResolver:     commandResolver,
		},
		transport: transport,
		host:      host,
		sessions:  make(map[string]*standardACPSession),
	}
}

func claudeACPEnv(session Session, host HostMetadata) []string {
	env := standardACPEnv(session, host)
	env = append(env, "IS_SANDBOX=1")
	return env
}

func claudeCodeCustomModel(session Session) string {
	model := strings.TrimSpace(session.SettingsValue().Model)
	if model == "" || claudeCodeACPModelAliases[model] {
		return ""
	}
	return model
}

func claudeACPInitializeParams(host HostMetadata) map[string]any {
	return map[string]any{
		"protocolVersion": acpProtocolVersion,
		"clientCapabilities": map[string]any{
			"fs": map[string]any{
				"readTextFile":  true,
				"writeTextFile": true,
			},
			"terminal": true,
			"auth": map[string]any{
				"terminal": true,
			},
			"_meta": map[string]any{
				"terminal_output": true,
				"terminal-auth":   true,
			},
		},
		"clientInfo": host.clientInfoParams(),
	}
}
