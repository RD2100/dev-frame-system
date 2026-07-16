package agentruntime

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	activityshared "github.com/tutti-os/tutti/packages/agent/daemon/activity/events"
)

// TestRealCodexAppServerTurn drives the adapter against the locally
// installed `codex app-server` binary. Gated behind an env var because it
// needs codex credentials and spends real tokens.
func TestRealCodexAppServerTurn(t *testing.T) {
	if os.Getenv("TUTTI_REAL_CODEX_TEST") == "" {
		t.Skip("set TUTTI_REAL_CODEX_TEST=1 to run against the real codex app-server")
	}
	workDir := t.TempDir()
	adapter := NewCodexAppServerAdapter(NewLocalProcessTransport())
	session := Session{
		RoomID:         "real-room",
		AgentSessionID: "real-session",
		Provider:       ProviderCodex,
		CWD:            workDir,
		Status:         SessionStatusReady,
	}
	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Second)
	defer cancel()
	events, err := adapter.Start(ctx, session)
	if err != nil {
		t.Fatalf("Start: %v", err)
	}
	if len(events) == 0 {
		t.Fatal("no start events")
	}
	state := adapter.SessionState(session)
	t.Logf("auth state: %s", state.AuthState)
	if state.AuthState != "authenticated" {
		t.Fatalf("not authenticated: %s", state.AuthState)
	}
	defer func() { _ = adapter.Close(context.Background(), session) }()

	var streamed []activityshared.Event
	turnEvents, err := adapter.Exec(ctx, session, []PromptContentBlock{{
		Type: "text",
		Text: "Reply with exactly the word PONG and nothing else. Do not run any commands.",
	}}, "", "real-turn-1", func(next []activityshared.Event) {
		streamed = append(streamed, next...)
	}, nil)
	if err != nil {
		t.Fatalf("Exec: %v", err)
	}
	var assistantText string
	var completed bool
	for _, event := range turnEvents {
		if event.Type == activityshared.EventMessageAppended && event.Payload.Role == activityshared.MessageRoleAssistant {
			assistantText = event.Payload.Content
		}
		if event.Type == activityshared.EventTurnCompleted && event.Payload.TurnOutcome == string(activityshared.TurnOutcomeCompleted) {
			completed = true
		}
	}
	t.Logf("streamed=%d total=%d assistant=%q completed=%v", len(streamed), len(turnEvents), assistantText, completed)
	if !completed {
		t.Fatalf("turn did not complete: %d events", len(turnEvents))
	}
	if !strings.Contains(strings.ToUpper(assistantText), "PONG") {
		t.Fatalf("assistant reply = %q, want PONG", assistantText)
	}
}
