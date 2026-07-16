package agent

import (
	"testing"

	agentsessionstore "github.com/tutti-os/tutti/packages/agent/daemon/activity"
)

// The state_patch push payload is the only live channel that updates the GUI
// activity record between reconciles. Dropping submitAvailability here leaves
// the record's blocked(active_turn) value from the send RPC in place forever,
// which strands queued prompts after the turn settles (the queued-prompt
// drain coordinator only dispatches on absent-or-available).
func TestActivityStatePatchEventPayloadForwardsSubmitAvailability(t *testing.T) {
	t.Parallel()

	activeTurnID := (*string)(nil)
	input := agentsessionstore.ReportSessionStateInput{
		WorkspaceID:    "workspace-1",
		AgentSessionID: "agent-session-1",
		State: agentsessionstore.WorkspaceAgentSessionStateUpdate{
			Provider:         "codex",
			CurrentPhase:     "idle",
			OccurredAtUnixMS: 1000,
			SubmitAvailability: &agentsessionstore.WorkspaceAgentSubmitAvailability{
				State: "available",
			},
			Turn: &agentsessionstore.WorkspaceAgentTurnStateUpdate{
				TurnID:       "turn-1",
				ActiveTurnID: activeTurnID,
				Phase:        "settled",
				Outcome:      "completed",
				SubmitAvailability: &agentsessionstore.WorkspaceAgentSubmitAvailability{
					State: "available",
				},
				CompletedAtUnixMS: 1000,
			},
		},
	}

	payload := activityStatePatchEventPayload(input, 1000)

	availability, ok := payload["submitAvailability"].(map[string]any)
	if !ok {
		t.Fatalf("payload submitAvailability = %#v, want map", payload["submitAvailability"])
	}
	if availability["state"] != "available" {
		t.Fatalf("submitAvailability state = %#v, want available", availability["state"])
	}
	turn, ok := payload["turn"].(map[string]any)
	if !ok {
		t.Fatalf("payload turn = %#v, want map", payload["turn"])
	}
	turnAvailability, ok := turn["submitAvailability"].(map[string]any)
	if !ok {
		t.Fatalf("turn submitAvailability = %#v, want map", turn["submitAvailability"])
	}
	if turnAvailability["state"] != "available" {
		t.Fatalf("turn submitAvailability state = %#v, want available", turnAvailability["state"])
	}
}

func TestActivityStatePatchEventPayloadForwardsBlockedReason(t *testing.T) {
	t.Parallel()

	input := agentsessionstore.ReportSessionStateInput{
		WorkspaceID:    "workspace-1",
		AgentSessionID: "agent-session-1",
		State: agentsessionstore.WorkspaceAgentSessionStateUpdate{
			Provider:         "codex",
			OccurredAtUnixMS: 1000,
			SubmitAvailability: &agentsessionstore.WorkspaceAgentSubmitAvailability{
				State:  "blocked",
				Reason: "active_turn",
			},
		},
	}

	payload := activityStatePatchEventPayload(input, 1000)

	availability, ok := payload["submitAvailability"].(map[string]any)
	if !ok {
		t.Fatalf("payload submitAvailability = %#v, want map", payload["submitAvailability"])
	}
	if availability["state"] != "blocked" || availability["reason"] != "active_turn" {
		t.Fatalf("submitAvailability = %#v, want blocked/active_turn", availability)
	}
}

func TestActivityStatePatchEventPayloadOmitsAbsentSubmitAvailability(t *testing.T) {
	t.Parallel()

	input := agentsessionstore.ReportSessionStateInput{
		WorkspaceID:    "workspace-1",
		AgentSessionID: "agent-session-1",
		State: agentsessionstore.WorkspaceAgentSessionStateUpdate{
			Provider:         "codex",
			OccurredAtUnixMS: 1000,
		},
	}

	payload := activityStatePatchEventPayload(input, 1000)

	if _, present := payload["submitAvailability"]; present {
		t.Fatalf("payload submitAvailability present without source value: %#v", payload["submitAvailability"])
	}
}
