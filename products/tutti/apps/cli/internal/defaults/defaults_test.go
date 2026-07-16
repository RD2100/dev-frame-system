package defaults

import (
	"path/filepath"
	"testing"
)

func TestResolveDefaultsFromEnvUsesGeneratedStateDefaults(t *testing.T) {
	t.Setenv("HOME", "/tmp/tutti-cli-home")
	t.Setenv("TUTTI_ENV", "development")
	t.Setenv("TUTTI_STATE_DIR", "")
	t.Setenv("TUTTID_RUN_DIR", "")
	t.Setenv("TUTTID_LISTENER_INFO_PATH", "")

	got := ResolveDefaultsFromEnv()

	if got.Runtime.Env != "development" {
		t.Fatalf("env = %q, want development", got.Runtime.Env)
	}
	wantRoot := filepath.Join("/tmp/tutti-cli-home", ".tutti-dev")
	if got.State.RootDir != wantRoot {
		t.Fatalf("root dir = %q, want %q", got.State.RootDir, wantRoot)
	}
	wantListenerInfo := filepath.Join(wantRoot, "run", "tuttid.listener.json")
	if got.State.TuttidListenerInfoPath != wantListenerInfo {
		t.Fatalf("listener info path = %q, want %q", got.State.TuttidListenerInfoPath, wantListenerInfo)
	}
}

func TestResolveDefaultsFromEnvHonorsListenerInfoOverride(t *testing.T) {
	t.Setenv("TUTTID_LISTENER_INFO_PATH", "/tmp/tuttid.listener.json")

	got := ResolveDefaultsFromEnv()

	if got.State.TuttidListenerInfoPath != "/tmp/tuttid.listener.json" {
		t.Fatalf("listener info path = %q", got.State.TuttidListenerInfoPath)
	}
}

func TestResolveDefaultsFromEnvAppliesOverrides(t *testing.T) {
	t.Setenv("TUTTI_ENV", "development")
	t.Setenv("TUTTI_STATE_DIR", "/tmp/tutti-state")
	t.Setenv("TUTTID_LISTENER_INFO_PATH", "/tmp/tuttid.listener.json")

	got := ResolveDefaultsFromEnv()

	if got.Runtime.Env != "development" {
		t.Fatalf("env = %q, want development", got.Runtime.Env)
	}
	if got.State.RootDir != "/tmp/tutti-state" {
		t.Fatalf("root dir = %q", got.State.RootDir)
	}
	if got.State.TuttidListenerInfoPath != "/tmp/tuttid.listener.json" {
		t.Fatalf("listener info path = %q", got.State.TuttidListenerInfoPath)
	}
}
