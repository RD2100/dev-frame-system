package agentruntime

// Hermes Agent's ACP provider config (`hermes acp`).

func NewHermesAdapter(transport ProcessTransport) *standardACPAdapter {
	return NewHermesAdapterWithHostMetadata(transport, LegacyHostMetadata())
}

func NewHermesAdapterWithHostMetadata(transport ProcessTransport, host HostMetadata) *standardACPAdapter {
	return &standardACPAdapter{
		config: standardACPConfig{
			provider:            ProviderHermes,
			adapterName:         "hermes-acp",
			command:             []string{"hermes", "acp"},
			defaultTitle:        "Hermes Agent",
			authRequiredMessage: "Hermes ACP requires authentication in the runtime VM; ensure Hermes host credentials are synced before starting Agent GUI",
			permissionModeID: func(string) string {
				return "yolo"
			},
			initializeParams: func() map[string]any { return defaultACPInitializeParams(host) },
			env:              func(session Session) []string { return standardACPEnv(session, host) },
		},
		transport: transport,
		host:      host,
		sessions:  make(map[string]*standardACPSession),
	}
}
