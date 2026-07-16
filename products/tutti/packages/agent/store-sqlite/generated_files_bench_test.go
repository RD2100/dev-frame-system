package storesqlite

import (
	"context"
	"fmt"
	"testing"
)

func BenchmarkStoreListWorkspaceGeneratedFiles(b *testing.B) {
	store := New(openTestDB(b), testOptions(&staticProjectPaths{}))
	ctx := context.Background()
	if err := store.Migrate(ctx); err != nil {
		b.Fatalf("Migrate() error = %v", err)
	}
	const workspaceID = "ws-agent-generated-files-bench"
	seedGeneratedFileBenchmarkMessages(b, ctx, store, workspaceID, 100, 50)

	b.Run("empty-query-limit-30", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			_, ok, err := store.ListWorkspaceGeneratedFiles(ctx, ListWorkspaceGeneratedFilesInput{
				WorkspaceID: workspaceID,
				Limit:       30,
			})
			if err != nil || !ok {
				b.Fatalf("ListWorkspaceGeneratedFiles() ok=%v error=%v", ok, err)
			}
		}
	})

	b.Run("miss-query-limit-30", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			_, ok, err := store.ListWorkspaceGeneratedFiles(ctx, ListWorkspaceGeneratedFilesInput{
				WorkspaceID: workspaceID,
				Query:       "definitely-no-match",
				Limit:       30,
			})
			if err != nil || !ok {
				b.Fatalf("ListWorkspaceGeneratedFiles() ok=%v error=%v", ok, err)
			}
		}
	})
}

func seedGeneratedFileBenchmarkMessages(
	b *testing.B,
	ctx context.Context,
	store *Store,
	workspaceID string,
	sessionCount int,
	messagesPerSession int,
) {
	b.Helper()
	for sessionIndex := 0; sessionIndex < sessionCount; sessionIndex++ {
		sessionID := fmt.Sprintf("session-%03d", sessionIndex)
		if _, err := store.ReportSessionState(ctx, SessionStateReport{
			WorkspaceID:      workspaceID,
			AgentSessionID:   sessionID,
			Origin:           "runtime",
			Provider:         "codex",
			Cwd:              fmt.Sprintf("/workspace/project-%02d", sessionIndex%10),
			Status:           "completed",
			OccurredAtUnixMS: int64(1000 + sessionIndex),
		}); err != nil {
			b.Fatalf("ReportSessionState(%s) error = %v", sessionID, err)
		}
		for messageIndex := 0; messageIndex < messagesPerSession; messageIndex++ {
			if _, err := store.ReportSessionMessages(ctx, SessionMessageReport{
				WorkspaceID:    workspaceID,
				AgentSessionID: sessionID,
				Origin:         "runtime",
				Messages: []MessageUpdate{{
					MessageID: fmt.Sprintf("message-%03d-%03d", sessionIndex, messageIndex),
					Role:      "assistant",
					Kind:      "tool_call",
					Status:    "completed",
					Payload: map[string]any{
						"toolName": "Write",
						"fileChanges": map[string]any{
							"files": []any{
								map[string]any{
									"path": fmt.Sprintf("generated/file-%03d-%03d.md", sessionIndex, messageIndex),
								},
							},
						},
					},
					OccurredAtUnixMS: int64(10_000 + sessionIndex*messagesPerSession + messageIndex),
				}},
			}); err != nil {
				b.Fatalf("ReportSessionMessages(%s) error = %v", sessionID, err)
			}
		}
	}
}
