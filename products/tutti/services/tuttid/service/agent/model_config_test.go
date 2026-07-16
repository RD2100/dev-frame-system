package agent

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadClaudeCodeConfiguredDefaultModelKeepsConcreteModel(t *testing.T) {
	configDir := t.TempDir()
	settingsPath := filepath.Join(configDir, "settings.json")
	if err := os.WriteFile(settingsPath, []byte(`{"model":"claude-opus-4-6"}`), 0o600); err != nil {
		t.Fatalf("write settings.json: %v", err)
	}
	t.Setenv("CLAUDE_CONFIG_DIR", configDir)

	if got := readClaudeCodeConfiguredDefaultModel(); got != "claude-opus-4-6" {
		t.Fatalf("readClaudeCodeConfiguredDefaultModel() = %q, want claude-opus-4-6", got)
	}
}
