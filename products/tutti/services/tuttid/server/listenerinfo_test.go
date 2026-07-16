package server

import (
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestWriteListenerInfoWritesEndpointAuth(t *testing.T) {
	stateDir := t.TempDir()
	t.Setenv("TUTTI_STATE_DIR", stateDir)
	t.Setenv("TUTTI_ENV", "production")

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer listener.Close()

	if err := WriteListenerInfo(listener, ListenerSpec{
		AccessToken: "desktop-session-token",
		Addr:        "127.0.0.1:0",
	}); err != nil {
		t.Fatalf("WriteListenerInfo: %v", err)
	}

	listenerInfoPath := filepath.Join(stateDir, "run", "tuttid.listener.json")
	content, err := os.ReadFile(listenerInfoPath)
	if err != nil {
		t.Fatalf("read listener info: %v", err)
	}

	var payload struct {
		Version int    `json:"version"`
		Addr    string `json:"addr"`
		Auth    struct {
			Scheme string `json:"scheme"`
			Token  string `json:"token"`
		} `json:"auth"`
	}
	if err := json.Unmarshal(content, &payload); err != nil {
		t.Fatalf("unmarshal listener info: %v", err)
	}
	if payload.Version != 1 {
		t.Fatalf("version = %d, want 1", payload.Version)
	}
	if payload.Addr != listener.Addr().String() {
		t.Fatalf("addr = %q, want %q", payload.Addr, listener.Addr().String())
	}
	if payload.Auth.Scheme != "bearer" {
		t.Fatalf("auth scheme = %q, want bearer", payload.Auth.Scheme)
	}
	if payload.Auth.Token != "desktop-session-token" {
		t.Fatalf("auth token = %q, want desktop-session-token", payload.Auth.Token)
	}

	if runtime.GOOS != "windows" {
		stat, err := os.Stat(listenerInfoPath)
		if err != nil {
			t.Fatalf("stat listener info: %v", err)
		}
		if got := stat.Mode().Perm(); got != 0o600 {
			t.Fatalf("listener info permissions = %o, want 600", got)
		}
	}
}

func TestWriteListenerInfoRequiresAccessToken(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer listener.Close()

	if err := WriteListenerInfo(listener, ListenerSpec{Addr: "127.0.0.1:0"}); err == nil {
		t.Fatal("expected missing access token to fail")
	}
}
