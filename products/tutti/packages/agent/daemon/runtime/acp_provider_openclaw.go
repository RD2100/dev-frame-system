package agentruntime

// OpenClaw's ACP provider config (`openclaw acp -v`). OpenClaw's
// session/set_mode maps to a gateway thinkingLevel rather than a permission
// channel, so the config declares no permission-mode mapping.

import (
	"fmt"
	"strings"
)

func NewOpenClawAdapter(transport ProcessTransport) *standardACPAdapter {
	return NewOpenClawAdapterWithHostMetadata(transport, LegacyHostMetadata())
}

func NewOpenClawAdapterWithHostMetadata(transport ProcessTransport, host HostMetadata) *standardACPAdapter {
	return &standardACPAdapter{
		config: standardACPConfig{
			provider:            ProviderOpenClaw,
			adapterName:         "openclaw-acp",
			command:             []string{"openclaw", "acp", "-v"},
			defaultTitle:        "OpenClaw",
			authRequiredMessage: "OpenClaw ACP requires authentication in the runtime VM; ensure OpenClaw host credentials are synced before starting Agent GUI",
			permissionModeID: func(string) string {
				// OpenClaw ACP maps session/set_mode modeId -> gateway thinkingLevel.
				// It is not a permission-mode channel, so sending approve-all /
				// approve-reads here is a protocol error.
				return ""
			},
			initializeParams: func() map[string]any { return defaultACPInitializeParams(host) },
			env:              func(session Session) []string { return openclawACPEnv(session, host) },
		},
		transport: transport,
		host:      host,
		sessions:  make(map[string]*standardACPSession),
	}
}

// openclawGatewayChatSessionKey selects the gateway sessionKey hint for OpenClaw GUI ACP.
// Without it, openclaw acp falls back to "acp:<uuid>", which makes the gateway treat the chat as an
// ACP-spawned session and require sessions.json metadata that this desktop flow never writes.
func openclawGatewayChatSessionKey(session Session, host HostMetadata) string {
	prefix := host.OpenClawSessionKeyPrefix
	if strings.TrimSpace(session.AgentSessionID) != "" {
		return fmt.Sprintf("%s%s", prefix, session.AgentSessionID)
	}
	return prefix + "desktop"
}

func openclawACPEnv(session Session, host HostMetadata) []string {
	env := standardACPEnv(session, host)
	// OpenClaw enables Node's module compile cache before its ACP runtime starts.
	// With routed ACP startup this can stall before JSON-RPC initialize responds.
	env = append(env, "NODE_DISABLE_COMPILE_CACHE=1")
	return env
}
