package app

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRotatingFileWriterRotatesActiveLogWithDateIndex(t *testing.T) {
	dir := t.TempDir()
	now := time.Date(2026, time.May, 5, 18, 0, 0, 0, time.UTC)

	writer, err := NewRotatingFileWriter(filepath.Join(dir, "tuttid.log"), RotatingFileWriterOptions{
		MaxSizeBytes: 5,
		MaxBackups:   10,
		MaxAgeDays:   14,
		Now:          func() time.Time { return now },
	})
	if err != nil {
		t.Fatalf("NewRotatingFileWriter: %v", err)
	}
	if _, err := writer.Write([]byte("hello")); err != nil {
		t.Fatalf("first Write: %v", err)
	}
	if _, err := writer.Write([]byte("world")); err != nil {
		t.Fatalf("second Write: %v", err)
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}

	rotatedPath := filepath.Join(dir, "tuttid.2026-05-05.log")
	activePath := filepath.Join(dir, "tuttid.log")
	rotated, err := os.ReadFile(rotatedPath)
	if err != nil {
		t.Fatalf("read rotated file: %v", err)
	}
	active, err := os.ReadFile(activePath)
	if err != nil {
		t.Fatalf("read active file: %v", err)
	}
	if string(rotated) != "hello" {
		t.Fatalf("rotated data = %q, want hello", string(rotated))
	}
	if string(active) != "world" {
		t.Fatalf("active data = %q, want world", string(active))
	}
}

func TestRotatingFileWriterRotatesOnCalendarDayChange(t *testing.T) {
	dir := t.TempDir()
	now := time.Date(2026, time.May, 5, 15, 59, 0, 0, time.UTC)

	writer, err := NewRotatingFileWriter(filepath.Join(dir, "tuttid.log"), RotatingFileWriterOptions{
		MaxSizeBytes: 1024,
		MaxBackups:   10,
		MaxAgeDays:   14,
		Now:          func() time.Time { return now },
	})
	if err != nil {
		t.Fatalf("NewRotatingFileWriter: %v", err)
	}
	if _, err := writer.Write([]byte("before\n")); err != nil {
		t.Fatalf("first Write: %v", err)
	}
	now = time.Date(2026, time.May, 6, 16, 1, 0, 0, time.UTC)
	if _, err := writer.Write([]byte("after\n")); err != nil {
		t.Fatalf("second Write: %v", err)
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}

	rotated, err := os.ReadFile(filepath.Join(dir, "tuttid.2026-05-05.log"))
	if err != nil {
		t.Fatalf("read rotated file: %v", err)
	}
	if string(rotated) != "before\n" {
		t.Fatalf("rotated data = %q, want before", string(rotated))
	}
}

func TestRotatingFileWriterPrunesDirectoryBudget(t *testing.T) {
	dir := t.TempDir()
	oldPath := filepath.Join(dir, "tuttid.2026-05-04.log")
	newPath := filepath.Join(dir, "tuttid.2026-05-05.1.log")
	if err := os.WriteFile(oldPath, []byte("older"), 0o644); err != nil {
		t.Fatalf("write old log: %v", err)
	}
	if err := os.WriteFile(newPath, []byte("newer"), 0o644); err != nil {
		t.Fatalf("write new log: %v", err)
	}

	oldTime := time.Date(2026, time.May, 4, 12, 0, 0, 0, time.UTC)
	newTime := time.Date(2026, time.May, 5, 12, 0, 0, 0, time.UTC)
	if err := os.Chtimes(oldPath, oldTime, oldTime); err != nil {
		t.Fatalf("chtimes old log: %v", err)
	}
	if err := os.Chtimes(newPath, newTime, newTime); err != nil {
		t.Fatalf("chtimes new log: %v", err)
	}

	writer, err := NewRotatingFileWriter(filepath.Join(dir, "tuttid.log"), RotatingFileWriterOptions{
		MaxBackups:    10,
		MaxAgeDays:    14,
		MaxTotalBytes: 9,
		Now:           func() time.Time { return time.Date(2026, time.May, 5, 18, 0, 0, 0, time.UTC) },
	})
	if err != nil {
		t.Fatalf("NewRotatingFileWriter: %v", err)
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}

	if _, err := os.Stat(oldPath); !os.IsNotExist(err) {
		t.Fatalf("oldest directory-budget candidate still exists or stat failed: %v", err)
	}
	if _, err := os.Stat(newPath); err != nil {
		t.Fatalf("newer rotated log missing: %v", err)
	}
}
