package workspace

import (
	"archive/zip"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestExtractAppPackageZipRejectsEntryOverExpandedSizeLimit(t *testing.T) {
	t.Parallel()

	archivePath := createZipArchiveForTest(t, []zipArchiveEntryForTest{
		{name: "large.bin", body: strings.Repeat("a", 11)},
	})
	destinationDir := t.TempDir()

	err := extractAppPackageZipWithLimits(archivePath, destinationDir, 1024*1024, 10)
	if err == nil || !strings.Contains(err.Error(), `app archive entry "large.bin" exceeds maximum size 10`) {
		t.Fatalf("extractAppPackageZipWithLimits() error = %v, want large entry error", err)
	}
	if _, statErr := os.Stat(filepath.Join(destinationDir, "large.bin")); !os.IsNotExist(statErr) {
		t.Fatalf("large entry stat error = %v, want not exist", statErr)
	}
}

func TestExtractAppPackageZipRejectsTotalExpandedSizeLimit(t *testing.T) {
	t.Parallel()

	archivePath := createZipArchiveForTest(t, []zipArchiveEntryForTest{
		{name: "first.txt", body: strings.Repeat("a", 6)},
		{name: "second.txt", body: strings.Repeat("b", 5)},
	})
	destinationDir := t.TempDir()

	err := extractAppPackageZipWithLimits(archivePath, destinationDir, 1024*1024, 10)
	if err == nil || !strings.Contains(err.Error(), "app archive exceeds maximum expanded size 10") {
		t.Fatalf("extractAppPackageZipWithLimits() error = %v, want total size error", err)
	}
	if _, statErr := os.Stat(filepath.Join(destinationDir, "first.txt")); statErr != nil {
		t.Fatalf("first entry stat error = %v", statErr)
	}
	if _, statErr := os.Stat(filepath.Join(destinationDir, "second.txt")); !os.IsNotExist(statErr) {
		t.Fatalf("second entry stat error = %v, want not exist", statErr)
	}
}

func TestDownloadAppArtifactRetriesTransientHTTPFailure(t *testing.T) {
	t.Parallel()

	var requests int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if atomic.AddInt32(&requests, 1) == 1 {
			http.Error(w, "try again", http.StatusBadGateway)
			return
		}
		_, _ = w.Write([]byte("artifact"))
	}))
	defer server.Close()

	destinationPath := filepath.Join(t.TempDir(), "artifact.zip")
	if err := downloadAppArtifact(context.Background(), server.Client(), server.URL, destinationPath); err != nil {
		t.Fatalf("downloadAppArtifact() error = %v", err)
	}
	if got := atomic.LoadInt32(&requests); got != 2 {
		t.Fatalf("request count = %d, want 2", got)
	}
	data, err := os.ReadFile(destinationPath)
	if err != nil {
		t.Fatalf("read artifact: %v", err)
	}
	if string(data) != "artifact" {
		t.Fatalf("artifact body = %q", data)
	}
}

func TestDownloadAppArtifactIdleTimeoutRemovesPartialFile(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("partial"))
		if flusher, ok := w.(http.Flusher); ok {
			flusher.Flush()
		}
		<-r.Context().Done()
	}))
	defer server.Close()

	destinationPath := filepath.Join(t.TempDir(), "artifact.zip")
	err := downloadAppArtifactWithPolicy(context.Background(), server.Client(), server.URL, destinationPath, appArtifactDownloadPolicy{
		attempts:       1,
		idleTimeout:    20 * time.Millisecond,
		retryBaseDelay: time.Millisecond,
	})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("downloadAppArtifact() error = %v, want context deadline exceeded", err)
	}
	if _, statErr := os.Stat(destinationPath); !errors.Is(statErr, os.ErrNotExist) {
		t.Fatalf("partial artifact stat error = %v, want not exist", statErr)
	}
}

type zipArchiveEntryForTest struct {
	name string
	body string
}

func createZipArchiveForTest(t *testing.T, entries []zipArchiveEntryForTest) string {
	t.Helper()

	archivePath := filepath.Join(t.TempDir(), "app.zip")
	target, err := os.Create(archivePath)
	if err != nil {
		t.Fatalf("create test archive: %v", err)
	}
	writer := zip.NewWriter(target)
	for _, entry := range entries {
		entryWriter, err := writer.Create(entry.name)
		if err != nil {
			t.Fatalf("create test archive entry: %v", err)
		}
		if _, err := entryWriter.Write([]byte(entry.body)); err != nil {
			t.Fatalf("write test archive entry: %v", err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("close test archive writer: %v", err)
	}
	if err := target.Close(); err != nil {
		t.Fatalf("close test archive: %v", err)
	}
	return archivePath
}
