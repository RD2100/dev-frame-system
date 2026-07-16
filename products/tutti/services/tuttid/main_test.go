package main

import (
	"context"
	"io"
	"log/slog"
	"os"
	"strconv"
	"testing"
	"time"

	tuttitypes "github.com/tutti-os/tutti/services/tuttid/types"
)

func TestContextWithDesktopParentMonitorCancelsWhenParentPIDIsGone(t *testing.T) {
	t.Setenv("TUTTI_DESKTOP_PARENT_PID", "999999999")

	ctx, cancel := contextWithDesktopParentMonitor(context.Background(), testLogger())
	defer cancel()

	select {
	case <-ctx.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("parent monitor did not cancel after missing parent pid")
	}
}

func TestContextWithDesktopParentMonitorKeepsStandaloneDaemonRunning(t *testing.T) {
	t.Setenv("TUTTI_DESKTOP_PARENT_PID", "")

	ctx, cancel := contextWithDesktopParentMonitor(context.Background(), testLogger())
	defer cancel()

	select {
	case <-ctx.Done():
		t.Fatal("standalone daemon context cancelled unexpectedly")
	case <-time.After(100 * time.Millisecond):
	}
}

func TestContextWithDesktopParentMonitorAcceptsLiveParentPID(t *testing.T) {
	t.Setenv("TUTTI_DESKTOP_PARENT_PID", strconv.Itoa(os.Getpid()))

	ctx, cancel := contextWithDesktopParentMonitor(context.Background(), testLogger())
	defer cancel()

	select {
	case <-ctx.Done():
		t.Fatal("live parent context cancelled unexpectedly")
	case <-time.After(100 * time.Millisecond):
	}
}

func TestProcessExists(t *testing.T) {
	if !tuttitypes.ProcessExists(os.Getpid()) {
		t.Fatal("ProcessExists(os.Getpid()) = false")
	}
	if tuttitypes.ProcessExists(-1) {
		t.Fatal("ProcessExists(-1) = true")
	}
}

func testLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}
