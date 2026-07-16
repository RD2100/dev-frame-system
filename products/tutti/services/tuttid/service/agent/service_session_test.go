package agent

import "testing"

// TestMergePersistedSessionStatePreservesImportedFlagWithLiveRuntimeContext
// guards against a regression where opening/resuming an imported Codex or
// Claude Code session dropped the "imported" RuntimeContext marker the
// moment the runtime controller held a live RuntimeSession for it. The
// frontend's unread-completion badge is explicitly suppressed for imported
// sessions (see agentGuiConversationListStore.ts's `isImported !== true`
// guard), so losing the marker made a just-read historical session's unread
// badge reappear once its runtime session activated.
func TestMergePersistedSessionStatePreservesImportedFlagWithLiveRuntimeContext(t *testing.T) {
	persisted := PersistedSession{
		RuntimeContext: map[string]any{
			"imported":                true,
			"externalImportNoProject": true,
			"externalSourcePath":      "/home/user/.codex/sessions/abc.jsonl",
		},
	}
	// A live RuntimeSession's own RuntimeContext is never empty in practice
	// (it carries the adapter's own bookkeeping), which is what defeats the
	// all-or-nothing "only fill in when empty" swap this merge used to rely
	// on exclusively.
	live := Session{
		RuntimeContext: map[string]any{
			"visible": true,
		},
	}

	merged := mergePersistedSessionState(live, persisted)

	if merged.RuntimeContext["imported"] != true {
		t.Fatalf("RuntimeContext = %#v, want imported preserved from persisted state", merged.RuntimeContext)
	}
	if merged.RuntimeContext["externalImportNoProject"] != true {
		t.Fatalf("RuntimeContext = %#v, want externalImportNoProject preserved from persisted state", merged.RuntimeContext)
	}
	if merged.RuntimeContext["externalSourcePath"] != "/home/user/.codex/sessions/abc.jsonl" {
		t.Fatalf("RuntimeContext = %#v, want externalSourcePath preserved from persisted state", merged.RuntimeContext)
	}
	if merged.RuntimeContext["visible"] != true {
		t.Fatalf("RuntimeContext = %#v, want live runtime's own keys kept", merged.RuntimeContext)
	}
}

// TestMergePersistedSessionStateDoesNotOverrideLiveImportFields ensures the
// merge never clobbers a live RuntimeContext value with a persisted one for
// the same key — it only fills in markers the live context doesn't already
// have an opinion on.
func TestMergePersistedSessionStateDoesNotOverrideLiveImportFields(t *testing.T) {
	persisted := PersistedSession{
		RuntimeContext: map[string]any{
			"imported": true,
		},
	}
	live := Session{
		RuntimeContext: map[string]any{
			"imported": false,
		},
	}

	merged := mergePersistedSessionState(live, persisted)

	if merged.RuntimeContext["imported"] != false {
		t.Fatalf("RuntimeContext = %#v, want live's own imported value kept as-is", merged.RuntimeContext)
	}
}

// TestMergePersistedSessionStateStillFillsEmptyLiveRuntimeContext keeps the
// original all-or-nothing behavior intact for sessions whose live
// RuntimeContext is genuinely empty (e.g. a freshly attached runtime that
// hasn't reported anything yet).
func TestMergePersistedSessionStateStillFillsEmptyLiveRuntimeContext(t *testing.T) {
	persisted := PersistedSession{
		RuntimeContext: map[string]any{
			"imported": true,
			"visible":  true,
		},
	}
	live := Session{}

	merged := mergePersistedSessionState(live, persisted)

	if merged.RuntimeContext["imported"] != true || merged.RuntimeContext["visible"] != true {
		t.Fatalf("RuntimeContext = %#v, want full persisted context copied when live context is empty", merged.RuntimeContext)
	}
}

// TestMergePersistedSessionStateHandlesEmptyPersistedRuntimeContext ensures a
// live RuntimeSession that never came from an import (no persisted
// RuntimeContext at all) is left untouched.
func TestMergePersistedSessionStateHandlesEmptyPersistedRuntimeContext(t *testing.T) {
	persisted := PersistedSession{}
	live := Session{
		RuntimeContext: map[string]any{
			"visible": true,
		},
	}

	merged := mergePersistedSessionState(live, persisted)

	if len(merged.RuntimeContext) != 1 || merged.RuntimeContext["visible"] != true {
		t.Fatalf("RuntimeContext = %#v, want live context unchanged", merged.RuntimeContext)
	}
}
