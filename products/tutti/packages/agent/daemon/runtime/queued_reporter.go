package agentruntime

import (
	"context"
	"errors"
	"strings"

	agentsessionstore "github.com/tutti-os/tutti/packages/agent/daemon/activity"
)

type QueuedReporter struct {
	ClientProvider func() ActivityClient
}

func (QueuedReporter) AsyncActivityReporter() {}

func (r QueuedReporter) Report(ctx context.Context, input agentsessionstore.ReportActivityInput) error {
	if len(input.TimelineItems) == 0 && len(input.StatePatches) == 0 && len(input.MessageUpdates) == 0 {
		return nil
	}
	input.Source.SessionOrigin = agentsessionstore.WorkspaceAgentSessionOriginRuntime
	if input.Connector == nil && strings.TrimSpace(input.Source.Provider) != "" {
		input.Connector = &agentsessionstore.ConnectorInfo{
			ID:      strings.TrimSpace(input.Source.Provider),
			Version: "agent-gui-runtime",
		}
	}
	if r.ClientProvider == nil {
		return errors.New("agent session activity client provider is nil")
	}
	client := r.ClientProvider()
	if client == nil {
		return errors.New("agent session activity client is nil")
	}
	_, err := reportSessionActivity(ctx, client, input)
	return err
}
