package agentruntime

import (
	"os"
	"path/filepath"
	"testing"
)

func TestClaudeSettingsBaseURLReadsUserSettingsEnv(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	settingsDir := filepath.Join(home, ".claude")
	if err := os.MkdirAll(settingsDir, 0o700); err != nil {
		t.Fatalf("create settings dir: %v", err)
	}
	if err := os.WriteFile(
		filepath.Join(settingsDir, "settings.json"),
		[]byte(`{"env":{"ANTHROPIC_BASE_URL":"https://anthropic.user.test"}}`),
		0o600,
	); err != nil {
		t.Fatalf("write settings: %v", err)
	}

	if got := claudeSettingsBaseURL(""); got != "https://anthropic.user.test" {
		t.Fatalf("claude settings base URL = %q, want user settings URL", got)
	}
}

func TestClaudeSettingsBaseURLPrefersProjectLocalSettings(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	if err := os.MkdirAll(filepath.Join(home, ".claude"), 0o700); err != nil {
		t.Fatalf("create user settings dir: %v", err)
	}
	if err := os.WriteFile(
		filepath.Join(home, ".claude", "settings.json"),
		[]byte(`{"env":{"ANTHROPIC_BASE_URL":"https://anthropic.user.test"}}`),
		0o600,
	); err != nil {
		t.Fatalf("write user settings: %v", err)
	}
	project := filepath.Join(t.TempDir(), "project", "nested")
	if err := os.MkdirAll(filepath.Join(project, ".claude"), 0o700); err != nil {
		t.Fatalf("create project settings dir: %v", err)
	}
	if err := os.WriteFile(
		filepath.Join(project, ".claude", "settings.local.json"),
		[]byte(`{"env":{"ANTHROPIC_BASE_URL":"https://anthropic.project.test"}}`),
		0o600,
	); err != nil {
		t.Fatalf("write project settings: %v", err)
	}

	if got := claudeSettingsBaseURL(project); got != "https://anthropic.project.test" {
		t.Fatalf("claude settings base URL = %q, want project settings URL", got)
	}
}
