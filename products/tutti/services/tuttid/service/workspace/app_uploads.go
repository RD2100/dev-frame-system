package workspace

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
	"unicode"

	"github.com/google/uuid"
)

const (
	WorkspaceAppUploadPurposeAppAsset = "app-asset"
	workspaceAppUploadTTL             = 15 * time.Minute
	workspaceAppUploadJanitorInterval = time.Minute
)

var (
	ErrInvalidWorkspaceAppUpload  = errors.New("invalid workspace app upload")
	ErrWorkspaceAppUploadExpired  = errors.New("workspace app upload expired")
	ErrWorkspaceAppUploadNotFound = errors.New("workspace app upload not found")
	ErrWorkspaceAppUploadNotReady = errors.New("workspace app upload content is not ready")
)

type PrepareWorkspaceAppUploadInput struct {
	MimeType  string
	Name      string
	Now       time.Time
	Purpose   string
	SizeBytes int64
}

type WorkspaceAppUploadSession struct {
	ExpiresAt time.Time
	UploadID  string
}

type PutWorkspaceAppUploadContentInput struct {
	Body io.Reader
	Now  time.Time
}

type WorkspaceAppUploadedFile struct {
	MimeType  string
	Name      string
	Path      string
	SHA256    string
	SizeBytes int64
}

type workspaceAppUploadSession struct {
	mu                sync.Mutex
	AppID             string
	Completed         bool
	ContentWritten    bool
	ExpiresAt         time.Time
	Extension         string
	FinalPath         string
	MimeType          string
	Name              string
	Purpose           string
	SHA256            string
	TempPath          string
	UploadID          string
	WorkspaceID       string
	ExpectedSizeBytes int64
	WrittenSizeBytes  int64
}

func (s *AppCenterService) PrepareWorkspaceAppUpload(
	ctx context.Context,
	workspaceID string,
	appID string,
	input PrepareWorkspaceAppUploadInput,
) (WorkspaceAppUploadSession, error) {
	workspaceID = strings.TrimSpace(workspaceID)
	appID = strings.TrimSpace(appID)
	if workspaceID == "" || appID == "" {
		return WorkspaceAppUploadSession{}, fmt.Errorf("%w: workspace id and app id are required", ErrInvalidWorkspaceAppUpload)
	}
	if _, _, err := s.installedPackage(ctx, workspaceID, appID); err != nil {
		return WorkspaceAppUploadSession{}, err
	}

	name := normalizeWorkspaceAppUploadName(input.Name)
	mimeType := normalizeWorkspaceAppUploadMimeType(input.MimeType)
	purpose := strings.TrimSpace(input.Purpose)
	if name == "" {
		return WorkspaceAppUploadSession{}, fmt.Errorf("%w: upload name is required", ErrInvalidWorkspaceAppUpload)
	}
	if mimeType == "" {
		return WorkspaceAppUploadSession{}, fmt.Errorf("%w: upload mime type is required", ErrInvalidWorkspaceAppUpload)
	}
	if purpose != WorkspaceAppUploadPurposeAppAsset {
		return WorkspaceAppUploadSession{}, fmt.Errorf("%w: upload purpose is unsupported", ErrInvalidWorkspaceAppUpload)
	}
	if input.SizeBytes < 0 {
		return WorkspaceAppUploadSession{}, fmt.Errorf("%w: upload size must not be negative", ErrInvalidWorkspaceAppUpload)
	}

	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	uploadID := uuid.NewString()
	expiresAt := now.Add(workspaceAppUploadTTL)
	session := &workspaceAppUploadSession{
		AppID:             appID,
		ExpiresAt:         expiresAt,
		Extension:         safeWorkspaceAppUploadExtension(name),
		MimeType:          mimeType,
		Name:              name,
		Purpose:           purpose,
		TempPath:          filepath.Join(s.workspaceAppUploadTempDir(workspaceID, appID), uploadID),
		UploadID:          uploadID,
		WorkspaceID:       workspaceID,
		ExpectedSizeBytes: input.SizeBytes,
	}

	s.cleanupExpiredWorkspaceAppUploadSessions(now)
	s.cleanupStaleWorkspaceAppUploadTempFiles(workspaceID, appID, now)
	s.uploadMu.Lock()
	if s.uploadSessions == nil {
		s.uploadSessions = make(map[string]*workspaceAppUploadSession)
	}
	s.uploadSessions[uploadID] = session
	s.uploadMu.Unlock()
	s.startWorkspaceAppUploadJanitor()

	return WorkspaceAppUploadSession{
		ExpiresAt: expiresAt,
		UploadID:  uploadID,
	}, nil
}

func (s *AppCenterService) PutWorkspaceAppUploadContent(
	ctx context.Context,
	workspaceID string,
	appID string,
	uploadID string,
	input PutWorkspaceAppUploadContentInput,
) error {
	_ = ctx
	session, err := s.workspaceAppUploadSession(workspaceID, appID, uploadID)
	if err != nil {
		return err
	}
	session.mu.Lock()
	defer session.mu.Unlock()
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	if input.Body == nil {
		return fmt.Errorf("%w: upload body is required", ErrInvalidWorkspaceAppUpload)
	}
	if now.After(session.ExpiresAt) {
		s.forgetWorkspaceAppUploadSession(uploadID)
		_ = os.Remove(session.TempPath)
		return ErrWorkspaceAppUploadExpired
	}
	if session.Completed {
		return fmt.Errorf("%w: upload is already completed", ErrInvalidWorkspaceAppUpload)
	}

	if err := os.MkdirAll(filepath.Dir(session.TempPath), 0o755); err != nil {
		return fmt.Errorf("create workspace app upload temp dir: %w", err)
	}
	tempFile, err := os.Create(session.TempPath)
	if err != nil {
		return fmt.Errorf("create workspace app upload temp file: %w", err)
	}

	hash := sha256.New()
	limitedBody := &io.LimitedReader{
		R: input.Body,
		N: workspaceAppUploadContentCopyLimit(session.ExpectedSizeBytes),
	}
	written, copyErr := io.Copy(tempFile, io.TeeReader(limitedBody, hash))
	closeErr := tempFile.Close()
	if copyErr != nil {
		_ = os.Remove(session.TempPath)
		return fmt.Errorf("write workspace app upload content: %w", copyErr)
	}
	if closeErr != nil {
		_ = os.Remove(session.TempPath)
		return fmt.Errorf("close workspace app upload content: %w", closeErr)
	}
	if written != session.ExpectedSizeBytes {
		_ = os.Remove(session.TempPath)
		session.ContentWritten = false
		session.SHA256 = ""
		session.WrittenSizeBytes = 0
		return fmt.Errorf(
			"%w: expected %d bytes, got %d",
			ErrInvalidWorkspaceAppUpload,
			session.ExpectedSizeBytes,
			written,
		)
	}

	session.ContentWritten = true
	session.SHA256 = hex.EncodeToString(hash.Sum(nil))
	session.WrittenSizeBytes = written
	return nil
}

func (s *AppCenterService) CompleteWorkspaceAppUpload(
	ctx context.Context,
	workspaceID string,
	appID string,
	uploadID string,
	now time.Time,
) (WorkspaceAppUploadedFile, error) {
	_ = ctx
	session, err := s.workspaceAppUploadSession(workspaceID, appID, uploadID)
	if err != nil {
		return WorkspaceAppUploadedFile{}, err
	}
	session.mu.Lock()
	defer session.mu.Unlock()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	if now.After(session.ExpiresAt) {
		s.forgetWorkspaceAppUploadSession(uploadID)
		_ = os.Remove(session.TempPath)
		return WorkspaceAppUploadedFile{}, ErrWorkspaceAppUploadExpired
	}
	if session.Completed {
		return uploadedWorkspaceAppFileFromSession(session), nil
	}
	if !session.ContentWritten || session.SHA256 == "" {
		return WorkspaceAppUploadedFile{}, ErrWorkspaceAppUploadNotReady
	}

	finalPath := filepath.Join(
		s.workspaceAppUploadDir(workspaceID, appID),
		session.SHA256[:2],
		session.SHA256+session.Extension,
	)
	if err := os.MkdirAll(filepath.Dir(finalPath), 0o755); err != nil {
		return WorkspaceAppUploadedFile{}, fmt.Errorf("create workspace app upload dir: %w", err)
	}
	if info, err := os.Stat(finalPath); err == nil {
		if !info.Mode().IsRegular() {
			return WorkspaceAppUploadedFile{}, fmt.Errorf("workspace app upload target is not a file: %s", finalPath)
		}
		_ = os.Remove(session.TempPath)
	} else if errors.Is(err, os.ErrNotExist) {
		if err := os.Rename(session.TempPath, finalPath); err != nil {
			return WorkspaceAppUploadedFile{}, fmt.Errorf("finalize workspace app upload: %w", err)
		}
	} else {
		return WorkspaceAppUploadedFile{}, fmt.Errorf("inspect workspace app upload target: %w", err)
	}

	session.Completed = true
	session.FinalPath = finalPath
	return uploadedWorkspaceAppFileFromSession(session), nil
}

func (s *AppCenterService) CancelWorkspaceAppUpload(
	ctx context.Context,
	workspaceID string,
	appID string,
	uploadID string,
) error {
	_ = ctx
	session, err := s.workspaceAppUploadSession(workspaceID, appID, uploadID)
	if err != nil {
		return err
	}
	s.forgetWorkspaceAppUploadSession(uploadID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if !session.Completed {
		_ = os.Remove(session.TempPath)
	}
	return nil
}

func (s *AppCenterService) workspaceAppUploadSession(
	workspaceID string,
	appID string,
	uploadID string,
) (*workspaceAppUploadSession, error) {
	workspaceID = strings.TrimSpace(workspaceID)
	appID = strings.TrimSpace(appID)
	uploadID = strings.TrimSpace(uploadID)
	if workspaceID == "" || appID == "" || uploadID == "" {
		return nil, fmt.Errorf("%w: workspace id, app id, and upload id are required", ErrInvalidWorkspaceAppUpload)
	}

	s.uploadMu.Lock()
	session := s.uploadSessions[uploadID]
	s.uploadMu.Unlock()
	if session == nil || session.WorkspaceID != workspaceID || session.AppID != appID {
		return nil, ErrWorkspaceAppUploadNotFound
	}
	return session, nil
}

func (s *AppCenterService) forgetWorkspaceAppUploadSession(uploadID string) {
	s.uploadMu.Lock()
	delete(s.uploadSessions, uploadID)
	s.uploadMu.Unlock()
}

func (s *AppCenterService) cleanupExpiredWorkspaceAppUploadSessions(now time.Time) {
	s.uploadMu.Lock()
	var expired []*workspaceAppUploadSession
	for uploadID, session := range s.uploadSessions {
		if now.After(session.ExpiresAt) {
			delete(s.uploadSessions, uploadID)
			expired = append(expired, session)
		}
	}
	s.uploadMu.Unlock()

	for _, session := range expired {
		session.mu.Lock()
		if !session.Completed {
			_ = os.Remove(session.TempPath)
		}
		session.mu.Unlock()
	}
}

func (s *AppCenterService) cleanupStaleWorkspaceAppUploadTempFiles(
	workspaceID string,
	appID string,
	now time.Time,
) {
	tempDir := s.workspaceAppUploadTempDir(workspaceID, appID)
	entries, err := os.ReadDir(tempDir)
	if err != nil {
		return
	}
	cutoff := now.Add(-workspaceAppUploadTTL)
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		if info.ModTime().After(cutoff) {
			continue
		}
		_ = os.Remove(filepath.Join(tempDir, entry.Name()))
	}
}

func (s *AppCenterService) startWorkspaceAppUploadJanitor() {
	s.uploadJanitorOnce.Do(func() {
		stop := make(chan struct{})
		s.uploadMu.Lock()
		s.uploadJanitorStop = stop
		s.uploadMu.Unlock()
		go s.runWorkspaceAppUploadJanitor(stop, s.workspaceAppUploadJanitorInterval())
	})
}

func (s *AppCenterService) runWorkspaceAppUploadJanitor(stop <-chan struct{}, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			s.cleanupExpiredWorkspaceAppUploadSessions(time.Now().UTC())
		case <-stop:
			return
		}
	}
}

func (s *AppCenterService) StopWorkspaceAppUploadJanitor() {
	s.uploadMu.Lock()
	stop := s.uploadJanitorStop
	s.uploadJanitorStop = nil
	s.uploadMu.Unlock()
	if stop != nil {
		close(stop)
	}
}

func (s *AppCenterService) workspaceAppUploadJanitorInterval() time.Duration {
	if s.uploadJanitorInterval > 0 {
		return s.uploadJanitorInterval
	}
	return workspaceAppUploadJanitorInterval
}

func workspaceAppUploadContentCopyLimit(expectedSizeBytes int64) int64 {
	if expectedSizeBytes == math.MaxInt64 {
		return math.MaxInt64
	}
	return expectedSizeBytes + 1
}

func (s *AppCenterService) workspaceAppUploadDir(workspaceID string, appID string) string {
	return filepath.Join(s.workspaceAppStateRoot(workspaceID, appID), "data", "uploads")
}

func (s *AppCenterService) workspaceAppUploadTempDir(workspaceID string, appID string) string {
	return filepath.Join(s.workspaceAppUploadDir(workspaceID, appID), ".tmp")
}

func uploadedWorkspaceAppFileFromSession(session *workspaceAppUploadSession) WorkspaceAppUploadedFile {
	return WorkspaceAppUploadedFile{
		MimeType:  session.MimeType,
		Name:      session.Name,
		Path:      session.FinalPath,
		SHA256:    session.SHA256,
		SizeBytes: session.WrittenSizeBytes,
	}
}

func normalizeWorkspaceAppUploadName(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	value = strings.ReplaceAll(value, "/", "_")
	value = strings.ReplaceAll(value, "\\", "_")
	return value
}

func normalizeWorkspaceAppUploadMimeType(value string) string {
	return strings.TrimSpace(value)
}

func safeWorkspaceAppUploadExtension(name string) string {
	extension := strings.ToLower(filepath.Ext(strings.TrimSpace(name)))
	if extension == "" || extension == "." || len(extension) > 32 {
		return ""
	}
	for index, char := range extension {
		if index == 0 && char == '.' {
			continue
		}
		if unicode.IsLetter(char) || unicode.IsDigit(char) {
			continue
		}
		return ""
	}
	return extension
}
