package workspace

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	workspacefiles "github.com/tutti-os/tutti/packages/workspace/files"
)

func TestFileServiceResolveWorkspaceRootDefaultsToUserHome(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)

	service := FileService{}

	root, err := service.ResolveWorkspaceRoot(context.Background(), " ws-1 ")
	if err != nil {
		t.Fatalf("ResolveWorkspaceRoot() error = %v", err)
	}

	if root.WorkspaceID != "ws-1" {
		t.Fatalf("workspace id = %q, want ws-1", root.WorkspaceID)
	}
	if root.PhysicalRoot != filepath.Clean(homeDir) {
		t.Fatalf("physical root = %q, want %q", root.PhysicalRoot, filepath.Clean(homeDir))
	}
	if root.LogicalRoot != filepath.Clean(homeDir) {
		t.Fatalf("logical root = %q, want %q", root.LogicalRoot, filepath.Clean(homeDir))
	}
}

func TestFileServiceListDirectoryAcceptsHomeAbsolutePaths(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)
	adapter := &fileSearchDeadlineAdapter{}
	service := FileService{Adapter: adapter}
	targetPath := filepath.Join(homeDir, ".tutti-dev", "agent", "runs")

	_, err := service.ListDirectory(context.Background(), "ws-1", workspacefiles.DirectoryListInput{
		IncludeHidden: true,
		Path:          targetPath,
	})
	if err != nil {
		t.Fatalf("ListDirectory() error = %v", err)
	}

	if adapter.listRoot.LogicalRoot != filepath.Clean(homeDir) {
		t.Fatalf("logical root = %q, want %q", adapter.listRoot.LogicalRoot, filepath.Clean(homeDir))
	}
	if adapter.listPath.String() != filepath.ToSlash(targetPath) {
		t.Fatalf("list path = %q, want %q", adapter.listPath, filepath.ToSlash(targetPath))
	}
	if !adapter.listIncludeHidden {
		t.Fatal("include hidden = false, want true")
	}
}

func TestFileServiceListDirectoryAcceptsExternalAbsolutePaths(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)
	adapter := &fileSearchDeadlineAdapter{}
	service := FileService{Adapter: adapter}
	targetPath := filepath.Join(t.TempDir(), "codex-presentations")

	_, err := service.ListDirectory(context.Background(), "ws-1", workspacefiles.DirectoryListInput{
		IncludeHidden: true,
		Path:          targetPath,
	})
	if err != nil {
		t.Fatalf("ListDirectory() error = %v", err)
	}

	wantRoot := filesystemRootForPath(targetPath)
	if adapter.listRoot.LogicalRoot != filepath.ToSlash(wantRoot) {
		t.Fatalf("logical root = %q, want %q", adapter.listRoot.LogicalRoot, filepath.ToSlash(wantRoot))
	}
	if adapter.listRoot.PhysicalRoot != wantRoot {
		t.Fatalf("physical root = %q, want %q", adapter.listRoot.PhysicalRoot, wantRoot)
	}
	if adapter.listPath.String() != filepath.ToSlash(filepath.Clean(targetPath)) {
		t.Fatalf("list path = %q, want %q", adapter.listPath, filepath.ToSlash(filepath.Clean(targetPath)))
	}
	if !adapter.listIncludeHidden {
		t.Fatal("include hidden = false, want true")
	}
}

func TestFileServiceResolveWorkspaceRootForPathRejectsUnsupportedSpecialPaths(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)
	service := FileService{}

	for _, path := range []string{
		"/dev/null",
		"/dev/./null",
		"/dev//null",
		"NUL",
		"NUL.txt",
		"C:\\tmp\\NUL",
	} {
		_, err := service.ResolveWorkspaceRootForPath(context.Background(), "ws-1", path)
		if !errors.Is(err, workspacefiles.ErrInvalidPath) {
			t.Fatalf("ResolveWorkspaceRootForPath(%q) error = %v, want ErrInvalidPath", path, err)
		}
	}
}

func TestFileServiceRenameEntryAcceptsExternalAbsolutePaths(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)
	adapter := &fileSearchDeadlineAdapter{}
	service := FileService{Adapter: adapter}
	targetPath := filepath.Join(t.TempDir(), "report.txt")

	_, err := service.RenameEntry(context.Background(), "ws-1", targetPath, "renamed.txt")
	if err != nil {
		t.Fatalf("RenameEntry() error = %v", err)
	}

	wantRoot := filesystemRootForPath(targetPath)
	if adapter.renameRoot.PhysicalRoot != wantRoot {
		t.Fatalf("rename physical root = %q, want %q", adapter.renameRoot.PhysicalRoot, wantRoot)
	}
	if adapter.renamePath.String() != filepath.ToSlash(filepath.Clean(targetPath)) {
		t.Fatalf("rename path = %q, want %q", adapter.renamePath, filepath.ToSlash(filepath.Clean(targetPath)))
	}
	if adapter.renameName != "renamed.txt" {
		t.Fatalf("rename name = %q", adapter.renameName)
	}
}

func TestFileServiceMoveEntryUsesExternalRootWhenTargetIsExternal(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)
	adapter := &fileSearchDeadlineAdapter{}
	service := FileService{Adapter: adapter}
	sourcePath := filepath.Join(homeDir, "project", "report.txt")
	targetDirectoryPath := filepath.Join(t.TempDir(), "output")

	_, err := service.MoveEntry(context.Background(), "ws-1", sourcePath, targetDirectoryPath)
	if err != nil {
		t.Fatalf("MoveEntry() error = %v", err)
	}

	wantRoot := filesystemRootForPath(targetDirectoryPath)
	if adapter.moveRoot.PhysicalRoot != wantRoot {
		t.Fatalf("move physical root = %q, want %q", adapter.moveRoot.PhysicalRoot, wantRoot)
	}
	if adapter.movePath.String() != filepath.ToSlash(filepath.Clean(sourcePath)) {
		t.Fatalf("move path = %q, want %q", adapter.movePath, filepath.ToSlash(filepath.Clean(sourcePath)))
	}
	if adapter.moveTargetDirectory.String() != filepath.ToSlash(filepath.Clean(targetDirectoryPath)) {
		t.Fatalf("move target = %q, want %q", adapter.moveTargetDirectory, filepath.ToSlash(filepath.Clean(targetDirectoryPath)))
	}
}

func TestFileServiceSearchSetsDefaultDeadline(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)
	adapter := &fileSearchDeadlineAdapter{}
	service := FileService{Adapter: adapter}

	before := time.Now()
	_, err := service.Search(context.Background(), "ws-1", workspacefiles.SearchInput{
		Query: "readme",
	})
	if err != nil {
		t.Fatalf("Search() error = %v", err)
	}

	if adapter.input.Deadline.IsZero() {
		t.Fatalf("deadline was not set")
	}
	if adapter.input.Deadline.Before(before) {
		t.Fatalf("deadline = %s, want after %s", adapter.input.Deadline, before)
	}
	maxDeadline := before.Add(defaultWorkspaceFileSearchBudget + 100*time.Millisecond)
	if adapter.input.Deadline.After(maxDeadline) {
		t.Fatalf("deadline = %s, want before %s", adapter.input.Deadline, maxDeadline)
	}
}

func TestFileServiceSearchPreservesExplicitDeadline(t *testing.T) {
	homeDir := t.TempDir()
	t.Setenv("HOME", homeDir)
	adapter := &fileSearchDeadlineAdapter{}
	service := FileService{Adapter: adapter}
	deadline := time.Now().Add(42 * time.Second)

	_, err := service.Search(context.Background(), "ws-1", workspacefiles.SearchInput{
		Deadline: deadline,
		Query:    "readme",
	})
	if err != nil {
		t.Fatalf("Search() error = %v", err)
	}
	if !adapter.input.Deadline.Equal(deadline) {
		t.Fatalf("deadline = %s, want %s", adapter.input.Deadline, deadline)
	}
}

type fileSearchDeadlineAdapter struct {
	input               workspacefiles.SearchInput
	listIncludeHidden   bool
	listPath            workspacefiles.LogicalPath
	listRoot            workspacefiles.WorkspaceRoot
	moveRoot            workspacefiles.WorkspaceRoot
	movePath            workspacefiles.LogicalPath
	moveTargetDirectory workspacefiles.LogicalPath
	renameRoot          workspacefiles.WorkspaceRoot
	renamePath          workspacefiles.LogicalPath
	renameName          string
}

func (a *fileSearchDeadlineAdapter) Search(
	_ context.Context,
	root workspacefiles.WorkspaceRoot,
	input workspacefiles.SearchInput,
) (workspacefiles.SearchResult, error) {
	a.input = input
	return workspacefiles.SearchResult{
		WorkspaceID: root.WorkspaceID,
		Root:        workspacefiles.LogicalPath(root.LogicalRoot),
		Entries:     []workspacefiles.SearchEntry{},
	}, nil
}

func (a *fileSearchDeadlineAdapter) ListDirectory(
	_ context.Context,
	root workspacefiles.WorkspaceRoot,
	logicalPath workspacefiles.LogicalPath,
	includeHidden bool,
) (workspacefiles.DirectoryListing, error) {
	a.listRoot = root
	a.listPath = logicalPath
	a.listIncludeHidden = includeHidden
	return workspacefiles.DirectoryListing{
		WorkspaceID:   root.WorkspaceID,
		Root:          workspacefiles.LogicalPath(root.LogicalRoot),
		DirectoryPath: logicalPath,
		Entries:       []workspacefiles.FileEntry{},
	}, nil
}

func (*fileSearchDeadlineAdapter) CreateFile(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
) (workspacefiles.FileEntry, error) {
	return workspacefiles.FileEntry{}, nil
}

func (*fileSearchDeadlineAdapter) CreateDirectory(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
) (workspacefiles.FileEntry, error) {
	return workspacefiles.FileEntry{}, nil
}

func (*fileSearchDeadlineAdapter) DeleteEntry(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
	workspacefiles.EntryKind,
) error {
	return nil
}

func (a *fileSearchDeadlineAdapter) MoveEntry(
	_ context.Context,
	workspaceRoot workspacefiles.WorkspaceRoot,
	logicalPath workspacefiles.LogicalPath,
	targetDirectoryPath workspacefiles.LogicalPath,
) (workspacefiles.FileEntry, error) {
	a.moveRoot = workspaceRoot
	a.movePath = logicalPath
	a.moveTargetDirectory = targetDirectoryPath
	return workspacefiles.FileEntry{Path: targetDirectoryPath, Kind: workspacefiles.EntryKindFile}, nil
}

func (a *fileSearchDeadlineAdapter) RenameEntry(
	_ context.Context,
	workspaceRoot workspacefiles.WorkspaceRoot,
	logicalPath workspacefiles.LogicalPath,
	newName string,
) (workspacefiles.FileEntry, error) {
	a.renameRoot = workspaceRoot
	a.renamePath = logicalPath
	a.renameName = newName
	return workspacefiles.FileEntry{Path: logicalPath, Kind: workspacefiles.EntryKindFile}, nil
}

func (*fileSearchDeadlineAdapter) CopyEntry(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
) (workspacefiles.FileEntry, error) {
	return workspacefiles.FileEntry{}, nil
}

func (*fileSearchDeadlineAdapter) PreflightUploadFiles(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
	[]string,
) ([]workspacefiles.UploadConflict, error) {
	return nil, nil
}

func (*fileSearchDeadlineAdapter) ReadFile(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
	int64,
) (workspacefiles.FileContent, error) {
	return workspacefiles.FileContent{}, nil
}

func (*fileSearchDeadlineAdapter) UploadFiles(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
	[]string,
	bool,
) ([]workspacefiles.FileEntry, error) {
	return nil, nil
}

func (*fileSearchDeadlineAdapter) WriteTextFile(
	context.Context,
	workspacefiles.WorkspaceRoot,
	workspacefiles.LogicalPath,
	string,
) (workspacefiles.FileEntry, error) {
	return workspacefiles.FileEntry{}, nil
}
