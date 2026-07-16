package reporter

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadOrCreateDeviceIDPersistsValue(t *testing.T) {
	stateDir := t.TempDir()

	first, err := loadOrCreateDeviceID(stateDir)
	if err != nil {
		t.Fatalf("loadOrCreateDeviceID first error = %v", err)
	}
	second, err := loadOrCreateDeviceID(stateDir)
	if err != nil {
		t.Fatalf("loadOrCreateDeviceID second error = %v", err)
	}

	if first == "" {
		t.Fatal("first device id is empty")
	}
	if first != second {
		t.Fatalf("device id changed: first=%q second=%q", first, second)
	}
	fileContent, err := os.ReadFile(filepath.Join(stateDir, "device_id"))
	if err != nil {
		t.Fatalf("read device_id error = %v", err)
	}
	if strings.TrimSpace(string(fileContent)) != first {
		t.Fatalf("device_id file = %q, want %q", string(fileContent), first)
	}
}

func TestLoadOrCreateDeviceIDReusesExistingTrimmedValue(t *testing.T) {
	stateDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(stateDir, "device_id"), []byte(" existing-id \n"), 0o644); err != nil {
		t.Fatalf("write device_id error = %v", err)
	}

	got, err := loadOrCreateDeviceID(stateDir)
	if err != nil {
		t.Fatalf("loadOrCreateDeviceID error = %v", err)
	}
	if got != "existing-id" {
		t.Fatalf("device id = %q, want existing-id", got)
	}
}
