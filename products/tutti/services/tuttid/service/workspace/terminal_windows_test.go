//go:build windows

package workspace

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"golang.org/x/sys/windows"
)

func TestWindowsTerminalSpaceDirCreatesAndReceivesOutput(t *testing.T) {
	spaceDir := filepath.Join(t.TempDir(), "tutti terminal test")
	if err := os.MkdirAll(spaceDir, 0755); err != nil {
		t.Fatal(err)
	}

	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{
		Cwd: &spaceDir,
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	if session.Status != TerminalStatusRunning {
		t.Fatalf("status = %q, want %q", session.Status, TerminalStatusRunning)
	}
	if session.Cwd == nil || *session.Cwd != spaceDir {
		t.Fatalf("cwd = %v, want %q", session.Cwd, spaceDir)
	}

	marker := "tutti-cmd-exec-marker-a1b2c3"
	if err := service.Write(context.Background(), "ws-1", session.ID, "echo "+marker+"\r\n"); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	var snapshot TerminalSnapshot
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		snapshot, err = service.Snapshot(context.Background(), "ws-1", session.ID)
		if err != nil {
			t.Fatalf("Snapshot() error = %v", err)
		}
		if strings.Count(snapshot.Data, marker) >= 2 {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatalf("snapshot data = %q, want at least 2 occurrences of %q (command echo + output)", snapshot.Data, marker)
}

func TestWindowsTerminalAttachStreamReceivesOutput(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	stream, err := service.AttachStream(context.Background(), "ws-1", session.ID, AttachTerminalInput{})
	if err != nil {
		t.Fatalf("AttachStream() error = %v", err)
	}
	defer stream.Close()

	marker := "stream-terminal-test-x7y8z9"
	if err := service.Write(context.Background(), "ws-1", session.ID, "echo "+marker+"\r\n"); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	deadline := time.After(10 * time.Second)
	for {
		select {
		case event := <-stream.Events:
			if event.Type == TerminalStreamEventOutput && strings.Contains(event.Data, marker) {
				if event.Seq == nil || *event.Seq <= 0 {
					t.Fatalf("stream event seq = %v, want positive sequence", event.Seq)
				}
				return
			}
		case <-deadline:
			t.Fatal("timed out waiting for terminal stream output")
		}
	}
}

func TestWindowsTerminalResizeUpdatesDimensions(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{
		Cols: intPtrWin(80),
		Rows: intPtrWin(24),
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	resized, err := service.Resize(context.Background(), "ws-1", session.ID, ResizeTerminalInput{
		Cols: 120,
		Rows: 40,
	})
	if err != nil {
		t.Fatalf("Resize() error = %v", err)
	}
	if resized.Cols != 120 || resized.Rows != 40 {
		t.Fatalf("resize = %dx%d, want 120x40", resized.Cols, resized.Rows)
	}
}

func TestWindowsTerminalNaturalExitCodeZero(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	stream, err := service.AttachStream(context.Background(), "ws-1", session.ID, AttachTerminalInput{})
	if err != nil {
		t.Fatalf("AttachStream() error = %v", err)
	}
	defer stream.Close()

	if err := service.Write(context.Background(), "ws-1", session.ID, "exit 0\r\n"); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	waitForSingleExitEvent(t, stream.Events, TerminalStatusExited, nil)
}

func TestWindowsTerminalNaturalExitNonZeroCode(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	stream, err := service.AttachStream(context.Background(), "ws-1", session.ID, AttachTerminalInput{})
	if err != nil {
		t.Fatalf("AttachStream() error = %v", err)
	}
	defer stream.Close()

	if err := service.Write(context.Background(), "ws-1", session.ID, "exit 7\r\n"); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	code7 := 7
	waitForSingleExitEvent(t, stream.Events, TerminalStatusFailed, &code7)
}

func TestWindowsTerminalForcedTerminateStopsChild(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	pid := getSessionPID(t, service, session.ID)

	if err := service.Write(context.Background(), "ws-1", session.ID, "ping -n 60 127.0.0.1 > nul\r\n"); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	time.Sleep(500 * time.Millisecond)

	terminated, err := service.Terminate(context.Background(), "ws-1", session.ID)
	if err != nil {
		t.Fatalf("Terminate() error = %v", err)
	}
	if terminated.Status != TerminalStatusExited {
		t.Fatalf("terminated status = %q, want %q", terminated.Status, TerminalStatusExited)
	}

	if err := service.Write(context.Background(), "ws-1", session.ID, "echo after-kill\r\n"); err == nil {
		t.Fatal("Write after terminate should return error")
	} else if err != ErrTerminalNotRunning {
		t.Fatalf("Write after terminate error = %v, want ErrTerminalNotRunning", err)
	}

	if !isProcessExited(pid) {
		t.Fatalf("process pid %d still running after terminate", pid)
	}
}

func TestWindowsTerminalRepeatedTerminateIsSafe(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	if err := service.Write(context.Background(), "ws-1", session.ID, "ping -n 30 127.0.0.1 > nul\r\n"); err != nil {
		t.Fatalf("Write() error = %v", err)
	}
	time.Sleep(300 * time.Millisecond)

	for i := 0; i < 3; i++ {
		terminated, err := service.Terminate(context.Background(), "ws-1", session.ID)
		if err != nil {
			t.Fatalf("Terminate() iteration %d error = %v", i, err)
		}
		if terminated.Status != TerminalStatusExited {
			t.Fatalf("iteration %d: status = %q, want %q", i, terminated.Status, TerminalStatusExited)
		}
	}
}

func TestWindowsTerminateDoesNotHang(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	if err := service.Write(context.Background(), "ws-1", session.ID, "ping -n 60 127.0.0.1 > nul\r\n"); err != nil {
		t.Fatalf("Write() error = %v", err)
	}
	time.Sleep(500 * time.Millisecond)

	done := make(chan struct{}, 1)
	go func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
		done <- struct{}{}
	}()

	select {
	case <-done:
	case <-time.After(10 * time.Second):
		t.Fatal("Terminate did not return within timeout - possible hang")
	}
}

func TestWindowsTerminalMetadataAndStateReplayOnAttach(t *testing.T) {
	service := &TerminalService{}

	session, err := service.Create(context.Background(), "ws-1", CreateTerminalInput{})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	t.Cleanup(func() {
		_, _ = service.Terminate(context.Background(), "ws-1", session.ID)
	})

	stream, err := service.AttachStream(context.Background(), "ws-1", session.ID, AttachTerminalInput{})
	if err != nil {
		t.Fatalf("AttachStream() error = %v", err)
	}

	var sawMetadata bool
	var sawState bool
	deadline := time.After(10 * time.Second)
	for !sawMetadata || !sawState {
		select {
		case event := <-stream.Events:
			switch event.Type {
			case TerminalStreamEventMeta:
				sawMetadata = true
				if event.RuntimeKind == nil || *event.RuntimeKind != "local" {
					t.Fatalf("metadata runtime kind = %v, want local", event.RuntimeKind)
				}
				if event.Cwd == nil || *event.Cwd == "" {
					t.Fatal("metadata cwd missing")
				}
			case TerminalStreamEventState:
				sawState = true
				if event.Status != TerminalStatusRunning {
					t.Fatalf("state status = %q, want %q", event.Status, TerminalStatusRunning)
				}
			}
		case <-deadline:
			t.Fatal("timed out waiting for metadata/state replay")
		}
	}

	stream.Close()

	detached, err := service.Get(context.Background(), "ws-1", session.ID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if detached.Status != TerminalStatusDetached {
		t.Fatalf("status after detach = %q, want %q", detached.Status, TerminalStatusDetached)
	}
}

func waitForSingleExitEvent(t *testing.T, events <-chan TerminalStreamEvent, wantStatus TerminalStatus, wantCode *int) {
	t.Helper()
	exitCount := 0
	var graceTimer <-chan time.Time

	deadline := time.After(15 * time.Second)
	for {
		if exitCount == 1 && graceTimer == nil {
			graceTimer = time.After(500 * time.Millisecond)
		}
		select {
		case event, ok := <-events:
			if !ok {
				t.Fatal("event channel closed before exit event")
			}
			if event.Type != TerminalStreamEventExit {
				continue
			}
			exitCount++
			if exitCount > 1 {
				t.Fatalf("received %d exit events, want exactly 1", exitCount)
			}
			if event.Status != wantStatus {
				t.Fatalf("exit event status = %q, want %q", event.Status, wantStatus)
			}
			if wantCode != nil {
				if event.Code == nil || *event.Code != *wantCode {
					t.Fatalf("exit code = %v, want %d", event.Code, *wantCode)
				}
			}
		case <-graceTimer:
			return
		case <-deadline:
			t.Fatal("timed out waiting for exit event")
		}
	}
}

func getSessionPID(t *testing.T, service *TerminalService, sessionID string) int {
	t.Helper()
	mgr := service.ensureManager()
	mgr.mu.Lock()
	rs := mgr.sessions[sessionID]
	mgr.mu.Unlock()
	if rs == nil {
		t.Fatal("runtime session not found")
	}
	return rs.backend.Pid()
}

func isProcessExited(pid int) bool {
	handle, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
	if err != nil {
		return true
	}
	defer windows.CloseHandle(handle)
	event, err := windows.WaitForSingleObject(handle, 3000)
	if err != nil {
		return false
	}
	return event == windows.WAIT_OBJECT_0
}

func intPtrWin(v int) *int { return &v }
