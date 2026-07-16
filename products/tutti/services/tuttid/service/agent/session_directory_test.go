package agent

import (
	"context"
	"path/filepath"
	"testing"
	"time"
)

func TestLocalSessionDirectoryAllocatorUsesAgentSessionsRoot(t *testing.T) {
	stateDir := t.TempDir()
	allocator := LocalSessionDirectoryAllocator{
		StateDir: stateDir,
		Now: func() time.Time {
			return time.Date(2026, 6, 22, 10, 0, 0, 0, time.UTC)
		},
	}

	path, err := allocator.CreateSessionDirectory(context.Background())
	if err != nil {
		t.Fatalf("CreateSessionDirectory() error = %v", err)
	}

	want := filepath.Join(stateDir, "agent", "sessions", "2026-06-22-001")
	if path != want {
		t.Fatalf("CreateSessionDirectory() = %q, want %q", path, want)
	}
}
