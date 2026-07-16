package agentruntime

import (
	"fmt"
	"strings"

	activityshared "github.com/tutti-os/tutti/packages/agent/daemon/activity/events"
)

// Cursor's ACP agent surfaces transient upstream failures (its HTTP/2 stream
// to the Cursor backend getting cut) as a plain trailing text chunk such as
//
//	Error: RetriableError: [canceled] http/2 stream closed with error code CANCEL (0x8)
//
// followed by a NORMAL session/prompt result — protocol-wise the turn looks
// successful, so the conversation silently stops mid-task and the user has to
// prod the agent to continue. cursor-agent classifies these as retriable
// itself; when a provider opts in (config.autoContinueRetriableTurnError) the
// adapter resumes the turn with a synthetic continue prompt a bounded number
// of times, and marks the turn failed once the retries are also cut short.
const acpAutoContinueMaxAttempts = 2

var acpRetriableTurnTailPrefixes = []string{
	"Error: RetriableError:",
	"Error: ConnectError:",
}

// acpRetriableTurnTailError returns the transient-error line when the turn's
// trailing assistant text ends with one.
func acpRetriableTurnTailError(text string) (string, bool) {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return "", false
	}
	lines := strings.Split(trimmed, "\n")
	last := strings.TrimSpace(lines[len(lines)-1])
	for _, prefix := range acpRetriableTurnTailPrefixes {
		if strings.HasPrefix(last, prefix) {
			return last, true
		}
	}
	return "", false
}

// acpStopReasonEndsTurnNormally reports whether the stop reason would take
// Exec's default (turn-completed) branch — the only state worth auto-continuing
// from. Canceled and hard-failure stop reasons keep their existing handling.
func acpStopReasonEndsTurnNormally(stopReason string) bool {
	switch stopReason {
	case "canceled", "refusal", "max_tokens", "max_turn_requests":
		return false
	default:
		return true
	}
}

// acpAutoContinuePromptContent is the synthetic prompt that resumes a turn cut
// short by a transient network error. It is deliberately not emitted as a
// user message: the provider session retains the full prior context, so the
// transcript shows the agent simply picking the work back up.
func acpAutoContinuePromptContent() []map[string]any {
	return []map[string]any{{
		"type": "text",
		"text": "The previous response was interrupted by a transient network error. Continue exactly where you left off; do not repeat work that already completed.",
	}}
}

// acpAutoContinueNoticeEvent renders the in-transcript banner that separates
// the error tail from the auto-continued output, so the retry is visible
// instead of the agent appearing to stutter.
func acpAutoContinueNoticeEvent(session Session, turnID string, errLine string, attempt int) (activityshared.Event, bool) {
	return acpSystemNoticeEvent(session, turnID, map[string]any{
		"kind":       "agent_system_notice",
		"noticeKind": "transport_retry",
		"severity":   "warning",
		"title":      fmt.Sprintf("Connection to the agent backend dropped; continuing automatically (%d/%d).", attempt, acpAutoContinueMaxAttempts),
		"detail":     errLine,
		"retryable":  true,
	}, "system_notice", true)
}
