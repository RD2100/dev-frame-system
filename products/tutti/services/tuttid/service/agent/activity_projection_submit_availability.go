package agent

import (
	"strings"

	agentsessionstore "github.com/tutti-os/tutti/packages/agent/daemon/activity"
)

func submitAvailabilityEventPayload(value *agentsessionstore.WorkspaceAgentSubmitAvailability) map[string]any {
	if value == nil {
		return nil
	}
	state := strings.TrimSpace(value.State)
	if state == "" {
		return nil
	}
	payload := map[string]any{"state": state}
	if reason := strings.TrimSpace(value.Reason); reason != "" {
		payload["reason"] = reason
	}
	return payload
}

func activityStatePatchEventPayload(
	input agentsessionstore.ReportSessionStateInput,
	lastEventUnixMS int64,
) map[string]any {
	state := input.State
	payload := map[string]any{
		"agentSessionId":   strings.TrimSpace(input.AgentSessionID),
		"eventType":        "state_patch",
		"lastEventUnixMs":  lastEventUnixMS,
		"occurredAtUnixMs": firstNonZeroInt64(state.OccurredAtUnixMS, lastEventUnixMS),
		"workspaceId":      strings.TrimSpace(input.WorkspaceID),
	}
	if provider := strings.TrimSpace(firstNonEmptyString(state.Provider, input.Source.Provider)); provider != "" {
		payload["provider"] = provider
	}
	if agentTargetID := strings.TrimSpace(firstNonEmptyString(state.AgentTargetID, input.Source.AgentTargetID)); agentTargetID != "" {
		payload["agentTargetId"] = agentTargetID
	}
	if providerSessionID := strings.TrimSpace(firstNonEmptyString(state.ProviderSessionID, input.Source.ProviderSessionID)); providerSessionID != "" {
		payload["providerSessionId"] = providerSessionID
	}
	if model := strings.TrimSpace(state.Model); model != "" {
		payload["model"] = model
	}
	if cwd := strings.TrimSpace(state.CWD); cwd != "" {
		payload["cwd"] = cwd
	}
	if title := strings.TrimSpace(sessionStateTitle(state)); title != "" {
		payload["title"] = title
	}
	if lifecycleStatus := strings.TrimSpace(state.LifecycleStatus); lifecycleStatus != "" {
		payload["lifecycleStatus"] = lifecycleStatus
	}
	if currentPhase := strings.TrimSpace(state.CurrentPhase); currentPhase != "" {
		payload["currentPhase"] = currentPhase
	}
	if lastError := strings.TrimSpace(state.LastError); lastError != "" {
		payload["lastError"] = lastError
	}
	if state.StartedAtUnixMS > 0 {
		payload["startedAtUnixMs"] = state.StartedAtUnixMS
	}
	if state.EndedAtUnixMS > 0 {
		payload["endedAtUnixMs"] = state.EndedAtUnixMS
	}
	// submitAvailability must ride every state patch: this push event is the
	// only live channel updating the GUI activity record between reconciles,
	// and a consumer left on a stale blocked(active_turn) after the turn
	// settles never dispatches its queued prompts.
	if availability := submitAvailabilityEventPayload(state.SubmitAvailability); availability != nil {
		payload["submitAvailability"] = availability
	}
	// runtimeContext must ride too: it carries backgroundAgents, which the
	// GUI needs to hold queued prompts while background agents are live; the
	// only other carrier is a manual reconcile fetch.
	if runtimeContext := clonePayload(state.RuntimeContext); len(runtimeContext) > 0 {
		payload["runtimeContext"] = runtimeContext
	}
	if state.Turn != nil {
		turn := map[string]any{
			"turnId": strings.TrimSpace(state.Turn.TurnID),
		}
		if phase := strings.TrimSpace(state.Turn.Phase); phase != "" {
			turn["phase"] = phase
		}
		if outcome := strings.TrimSpace(state.Turn.Outcome); outcome != "" {
			turn["outcome"] = outcome
		}
		if availability := submitAvailabilityEventPayload(state.Turn.SubmitAvailability); availability != nil {
			turn["submitAvailability"] = availability
		}
		if state.Turn.FileChanges != nil {
			turn["fileChanges"] = clonePayload(state.Turn.FileChanges)
		}
		if state.Turn.StartedAtUnixMS > 0 {
			turn["startedAtUnixMs"] = state.Turn.StartedAtUnixMS
		}
		if state.Turn.CompletedAtUnixMS > 0 {
			turn["completedAtUnixMs"] = state.Turn.CompletedAtUnixMS
		}
		payload["turn"] = turn
	}
	return payload
}
