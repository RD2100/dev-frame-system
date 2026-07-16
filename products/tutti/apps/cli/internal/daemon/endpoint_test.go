package daemon

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadEndpointFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "tuttid.listener.json")
	if err := os.WriteFile(path, []byte(`{"version":1,"addr":"127.0.0.1:4545","auth":{"scheme":"bearer","token":"token-1"}}`), 0o600); err != nil {
		t.Fatalf("write endpoint: %v", err)
	}

	endpoint, err := ReadEndpointFile(path)
	if err != nil {
		t.Fatalf("ReadEndpointFile: %v", err)
	}
	if endpoint.Addr != "127.0.0.1:4545" {
		t.Fatalf("addr = %q", endpoint.Addr)
	}
	if endpoint.Token != "token-1" {
		t.Fatalf("token = %q", endpoint.Token)
	}
}

func TestReadEndpointFileRejectsMissingAuth(t *testing.T) {
	path := filepath.Join(t.TempDir(), "tuttid.listener.json")
	if err := os.WriteFile(path, []byte(`{"addr":"127.0.0.1:4545"}`), 0o600); err != nil {
		t.Fatalf("write endpoint: %v", err)
	}

	if _, err := ReadEndpointFile(path); err == nil {
		t.Fatal("expected missing auth to fail")
	}
}

func TestListenerInfoPathUsesStateRoot(t *testing.T) {
	stateDir := t.TempDir()
	t.Setenv("TUTTI_STATE_DIR", stateDir)
	t.Setenv("TUTTID_RUN_DIR", "")
	t.Setenv("TUTTID_LISTENER_INFO_PATH", "")

	want := filepath.Join(stateDir, "run", "tuttid.listener.json")
	if got := ListenerInfoPath(); got != want {
		t.Fatalf("ListenerInfoPath() = %q, want %q", got, want)
	}
}
