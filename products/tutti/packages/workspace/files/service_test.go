package workspacefiles

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeResolver struct {
	root WorkspaceRoot
	err  error
}

func (r fakeResolver) ResolveWorkspaceRoot(_ context.Context, workspaceID string) (WorkspaceRoot, error) {
	if r.err != nil {
		return WorkspaceRoot{}, r.err
	}
	root := r.root
	if root.WorkspaceID == "" {
		root.WorkspaceID = workspaceID
	}
	return root, nil
}

type fakePathAwareResolver struct {
	fakeResolver
	rootByPath map[string]WorkspaceRoot
}

func (r fakePathAwareResolver) ResolveWorkspaceRootForPath(ctx context.Context, workspaceID string, path string) (WorkspaceRoot, error) {
	if root, ok := r.rootByPath[path]; ok {
		if root.WorkspaceID == "" {
			root.WorkspaceID = workspaceID
		}
		return root, nil
	}
	return r.ResolveWorkspaceRoot(ctx, workspaceID)
}

type fakeAdapter struct {
	directoryListingByPath   map[LogicalPath]DirectoryListing
	listDirectoryCallsByPath map[LogicalPath]int
	listDirectoryDelayByPath map[LogicalPath]time.Duration
	listDirectoryErrByPath   map[LogicalPath]error
	listRoot                 WorkspaceRoot
	listPath                 LogicalPath
	listIncludeHidden        bool
	createFile               LogicalPath
	readFile                 LogicalPath
	readMaxBytes             int64
	writeTextFile            LogicalPath
	writeTextContent         string
	createDir                LogicalPath
	deletePath               LogicalPath
	deleteKind               EntryKind
	moveRoot                 WorkspaceRoot
	movePath                 LogicalPath
	moveTargetDirectory      LogicalPath
	renameRoot               WorkspaceRoot
	renamePath               LogicalPath
	renameName               string
	conflicts                []UploadConflict
	uploadDir                LogicalPath
	uploadPaths              []string
	overwrite                bool
	searchInput              SearchInput
}

func (a *fakeAdapter) ListDirectory(ctx context.Context, root WorkspaceRoot, logicalPath LogicalPath, includeHidden bool) (DirectoryListing, error) {
	a.listRoot = root
	a.listPath = logicalPath
	a.listIncludeHidden = includeHidden
	if a.listDirectoryCallsByPath != nil {
		a.listDirectoryCallsByPath[logicalPath]++
	}
	if delay := a.listDirectoryDelayByPath[logicalPath]; delay > 0 {
		timer := time.NewTimer(delay)
		defer timer.Stop()
		select {
		case <-ctx.Done():
			return DirectoryListing{}, ctx.Err()
		case <-timer.C:
		}
	}
	if err := a.listDirectoryErrByPath[logicalPath]; err != nil {
		return DirectoryListing{}, err
	}
	if listing, ok := a.directoryListingByPath[logicalPath]; ok {
		return listing, nil
	}
	return DirectoryListing{
		Root:          NormalizeLogicalRoot(root.LogicalRoot),
		DirectoryPath: logicalPath,
		Entries: []FileEntry{
			{Path: "/workspace/README.md", Name: "README.md", Kind: EntryKindFile},
		},
	}, nil
}

type prefetchPolicyAdapter struct {
	*fakeAdapter
	blockedPaths map[LogicalPath]struct{}
}

func (a prefetchPolicyAdapter) ShouldPrefetchDirectory(_ WorkspaceRoot, logicalPath LogicalPath) bool {
	_, blocked := a.blockedPaths[logicalPath]
	return !blocked
}

func (a *fakeAdapter) CreateFile(_ context.Context, _ WorkspaceRoot, logicalPath LogicalPath) (FileEntry, error) {
	a.createFile = logicalPath
	return FileEntry{Path: logicalPath, Kind: EntryKindFile}, nil
}

func (a *fakeAdapter) ReadFile(_ context.Context, _ WorkspaceRoot, logicalPath LogicalPath, maxBytes int64) (FileContent, error) {
	a.readFile = logicalPath
	a.readMaxBytes = maxBytes
	return FileContent{
		Path:  logicalPath,
		Name:  LogicalPathBase(logicalPath),
		Bytes: []byte("hello"),
	}, nil
}

func (a *fakeAdapter) WriteTextFile(_ context.Context, _ WorkspaceRoot, logicalPath LogicalPath, content string) (FileEntry, error) {
	a.writeTextFile = logicalPath
	a.writeTextContent = content
	return FileEntry{Path: logicalPath, Kind: EntryKindFile}, nil
}

func (a *fakeAdapter) CreateDirectory(_ context.Context, _ WorkspaceRoot, logicalPath LogicalPath) (FileEntry, error) {
	a.createDir = logicalPath
	return FileEntry{Path: logicalPath, Kind: EntryKindDirectory}, nil
}

func (a *fakeAdapter) DeleteEntry(_ context.Context, _ WorkspaceRoot, logicalPath LogicalPath, kind EntryKind) error {
	a.deletePath = logicalPath
	a.deleteKind = kind
	return nil
}

func (a *fakeAdapter) MoveEntry(_ context.Context, root WorkspaceRoot, logicalPath LogicalPath, targetDirectoryPath LogicalPath) (FileEntry, error) {
	a.moveRoot = root
	a.movePath = logicalPath
	a.moveTargetDirectory = targetDirectoryPath
	return FileEntry{
		Path: LogicalPath(targetDirectoryPath.String() + "/" + LogicalPathBase(logicalPath)),
		Kind: EntryKindFile,
	}, nil
}

func (a *fakeAdapter) RenameEntry(_ context.Context, root WorkspaceRoot, logicalPath LogicalPath, newName string) (FileEntry, error) {
	a.renameRoot = root
	a.renamePath = logicalPath
	a.renameName = newName
	parentDirectoryPath := LogicalPathDir(logicalPath)
	return FileEntry{
		Path: LogicalPath(parentDirectoryPath.String() + "/" + newName),
		Kind: EntryKindFile,
	}, nil
}

func (*fakeAdapter) CopyEntry(_ context.Context, _ WorkspaceRoot, logicalPath LogicalPath) (FileEntry, error) {
	parentDirectoryPath := LogicalPathDir(logicalPath)
	baseName := LogicalPathBase(logicalPath)
	return FileEntry{
		Path: LogicalPath(parentDirectoryPath.String() + "/" + baseName + " copy"),
		Kind: EntryKindFile,
	}, nil
}

func (a *fakeAdapter) PreflightUploadFiles(_ context.Context, _ WorkspaceRoot, targetDirectoryPath LogicalPath, sourcePaths []string) ([]UploadConflict, error) {
	a.uploadDir = targetDirectoryPath
	a.uploadPaths = append([]string(nil), sourcePaths...)
	return append([]UploadConflict(nil), a.conflicts...), nil
}

func (a *fakeAdapter) UploadFiles(_ context.Context, _ WorkspaceRoot, targetDirectoryPath LogicalPath, sourcePaths []string, overwrite bool) ([]FileEntry, error) {
	a.uploadDir = targetDirectoryPath
	a.uploadPaths = append([]string(nil), sourcePaths...)
	a.overwrite = overwrite
	return []FileEntry{
		{Path: "/workspace/docs/readme.md", Name: "readme.md", Kind: EntryKindFile},
	}, nil
}

func (a *fakeAdapter) Search(_ context.Context, root WorkspaceRoot, input SearchInput) (SearchResult, error) {
	a.searchInput = input
	return SearchResult{
		WorkspaceID: root.WorkspaceID,
		Root:        NormalizeLogicalRoot(root.LogicalRoot),
		Entries: []SearchEntry{
			{Path: "/workspace/README.md", Name: "README.md", Kind: EntryKindFile},
		},
	}, nil
}

func TestServiceListDirectoryNormalizesPath(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	listing, err := service.ListDirectory(context.Background(), "ws-1", DirectoryListInput{
		Path: "src/../docs",
	})
	if err != nil {
		t.Fatalf("ListDirectory() error = %v", err)
	}
	if adapter.listPath != "/workspace/docs" {
		t.Fatalf("adapter path = %q", adapter.listPath)
	}
	if listing.WorkspaceID != "ws-1" {
		t.Fatalf("listing workspace id = %q", listing.WorkspaceID)
	}
	if len(listing.Entries) != 1 {
		t.Fatalf("entries length = %d", len(listing.Entries))
	}
}

func TestServiceListDirectoryUsesPathAwareRootForExternalAbsolutePath(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakePathAwareResolver{
			fakeResolver: fakeResolver{
				root: WorkspaceRoot{
					LogicalRoot:  "/Users/example",
					PhysicalRoot: "/Users/example",
				},
			},
			rootByPath: map[string]WorkspaceRoot{
				"/var/folders/demo/T/codex-presentations": {
					LogicalRoot:  "/",
					PhysicalRoot: "/",
				},
			},
		},
		Adapter: adapter,
	}

	_, err := service.ListDirectory(context.Background(), "ws-1", DirectoryListInput{
		Path: "/var/folders/demo/T/codex-presentations",
	})
	if err != nil {
		t.Fatalf("ListDirectory() error = %v", err)
	}
	if adapter.listRoot.LogicalRoot != "/" || adapter.listRoot.PhysicalRoot != "/" {
		t.Fatalf("list root = %+v, want filesystem root", adapter.listRoot)
	}
	if adapter.listPath != "/var/folders/demo/T/codex-presentations" {
		t.Fatalf("list path = %q", adapter.listPath)
	}
}

func TestServiceRenameEntryUsesPathAwareRootForExternalAbsolutePath(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakePathAwareResolver{
			fakeResolver: fakeResolver{
				root: WorkspaceRoot{
					LogicalRoot:  "/Users/example",
					PhysicalRoot: "/Users/example",
				},
			},
			rootByPath: map[string]WorkspaceRoot{
				"/tmp/report.txt": {
					LogicalRoot:  "/",
					PhysicalRoot: "/",
				},
			},
		},
		Adapter: adapter,
	}

	entry, err := service.RenameEntry(context.Background(), "ws-1", "/tmp/report.txt", "renamed.txt")
	if err != nil {
		t.Fatalf("RenameEntry() error = %v", err)
	}
	if adapter.renameRoot.LogicalRoot != "/" || adapter.renameRoot.PhysicalRoot != "/" {
		t.Fatalf("rename root = %+v, want filesystem root", adapter.renameRoot)
	}
	if adapter.renamePath != "/tmp/report.txt" {
		t.Fatalf("rename path = %q", adapter.renamePath)
	}
	if adapter.renameName != "renamed.txt" {
		t.Fatalf("rename name = %q", adapter.renameName)
	}
	if entry.Path != "/tmp/renamed.txt" {
		t.Fatalf("renamed entry path = %q", entry.Path)
	}
}

func TestServiceMoveEntryUsesPathAwareRootWhenTargetIsExternal(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakePathAwareResolver{
			fakeResolver: fakeResolver{
				root: WorkspaceRoot{
					LogicalRoot:  "/Users/example",
					PhysicalRoot: "/Users/example",
				},
			},
			rootByPath: map[string]WorkspaceRoot{
				"/tmp/output": {
					LogicalRoot:  "/",
					PhysicalRoot: "/",
				},
			},
		},
		Adapter: adapter,
	}

	entry, err := service.MoveEntry(
		context.Background(),
		"ws-1",
		"/Users/example/project/report.txt",
		"/tmp/output",
	)
	if err != nil {
		t.Fatalf("MoveEntry() error = %v", err)
	}
	if adapter.moveRoot.LogicalRoot != "/" || adapter.moveRoot.PhysicalRoot != "/" {
		t.Fatalf("move root = %+v, want filesystem root", adapter.moveRoot)
	}
	if adapter.movePath != "/Users/example/project/report.txt" {
		t.Fatalf("move path = %q", adapter.movePath)
	}
	if adapter.moveTargetDirectory != "/tmp/output" {
		t.Fatalf("move target = %q", adapter.moveTargetDirectory)
	}
	if entry.Path != "/tmp/output/report.txt" {
		t.Fatalf("moved entry path = %q", entry.Path)
	}
}

func TestServiceMoveEntryRejectsDefaultRootWhenTargetIsExternal(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakePathAwareResolver{
			fakeResolver: fakeResolver{
				root: WorkspaceRoot{
					LogicalRoot:  "/Users/example",
					PhysicalRoot: "/Users/example",
				},
			},
			rootByPath: map[string]WorkspaceRoot{
				"/tmp/output": {
					LogicalRoot:  "/",
					PhysicalRoot: "/",
				},
			},
		},
		Adapter: adapter,
	}

	for _, value := range []string{"/Users/example", ""} {
		_, err := service.MoveEntry(
			context.Background(),
			"ws-1",
			value,
			"/tmp/output",
		)
		if !errors.Is(err, ErrRootDeleteForbidden) {
			t.Fatalf("MoveEntry(%q) error = %v, want ErrRootDeleteForbidden", value, err)
		}
		if adapter.movePath != "" {
			t.Fatalf("adapter move path = %q, want no call", adapter.movePath)
		}
	}
}

func TestServiceMoveEntryKeepsRelativeSourceUnderDefaultRootWhenTargetIsExternal(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakePathAwareResolver{
			fakeResolver: fakeResolver{
				root: WorkspaceRoot{
					LogicalRoot:  "/Users/example",
					PhysicalRoot: "/Users/example",
				},
			},
			rootByPath: map[string]WorkspaceRoot{
				"/tmp/output": {
					LogicalRoot:  "/",
					PhysicalRoot: "/",
				},
			},
		},
		Adapter: adapter,
	}

	entry, err := service.MoveEntry(
		context.Background(),
		"ws-1",
		"project/report.txt",
		"/tmp/output",
	)
	if err != nil {
		t.Fatalf("MoveEntry() error = %v", err)
	}
	if adapter.moveRoot.LogicalRoot != "/" || adapter.moveRoot.PhysicalRoot != "/" {
		t.Fatalf("move root = %+v, want filesystem root", adapter.moveRoot)
	}
	if adapter.movePath != "/Users/example/project/report.txt" {
		t.Fatalf("move path = %q", adapter.movePath)
	}
	if adapter.moveTargetDirectory != "/tmp/output" {
		t.Fatalf("move target = %q", adapter.moveTargetDirectory)
	}
	if entry.Path != "/tmp/output/report.txt" {
		t.Fatalf("moved entry path = %q", entry.Path)
	}
}

func TestServiceForwardsDirectoryHiddenToggle(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	_, err := service.ListDirectory(context.Background(), "ws-1", DirectoryListInput{
		IncludeHidden: true,
		Path:          "/workspace",
	})
	if err != nil {
		t.Fatalf("ListDirectory() error = %v", err)
	}
	if !adapter.listIncludeHidden {
		t.Fatal("expected includeHidden to be forwarded to the adapter")
	}
}

func TestServiceWriteTextFileNormalizesPath(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	entry, err := service.WriteTextFile(context.Background(), "ws-1", "docs/../README.md", "updated")
	if err != nil {
		t.Fatalf("WriteTextFile() error = %v", err)
	}
	if entry.Path != "/workspace/README.md" {
		t.Fatalf("WriteTextFile entry path = %q", entry.Path)
	}
	if adapter.writeTextFile != "/workspace/README.md" {
		t.Fatalf("WriteTextFile normalized path = %q", adapter.writeTextFile)
	}
	if adapter.writeTextContent != "updated" {
		t.Fatalf("WriteTextFile content = %q", adapter.writeTextContent)
	}
}

func TestServiceReadFileNormalizesPathAndBudget(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	content, err := service.ReadFile(context.Background(), "ws-1", "docs/../README.md", 1024)
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	if content.Path != "/workspace/README.md" {
		t.Fatalf("ReadFile content path = %q", content.Path)
	}
	if string(content.Bytes) != "hello" {
		t.Fatalf("ReadFile content = %q", content.Bytes)
	}
	if adapter.readFile != "/workspace/README.md" {
		t.Fatalf("ReadFile normalized path = %q", adapter.readFile)
	}
	if adapter.readMaxBytes != 1024 {
		t.Fatalf("ReadFile max bytes = %d", adapter.readMaxBytes)
	}
}

func TestServiceGetDirectoryTreeSnapshotPrefetchesNestedDirectories(t *testing.T) {
	adapter := &fakeAdapter{
		directoryListingByPath: map[LogicalPath]DirectoryListing{
			"/workspace": {
				DirectoryPath: "/workspace",
				Entries: []FileEntry{
					{
						Path:        "/workspace/docs",
						Name:        "docs",
						Kind:        EntryKindDirectory,
						HasChildren: true,
					},
				},
			},
			"/workspace/docs": {
				DirectoryPath: "/workspace/docs",
				Entries: []FileEntry{
					{
						Path:        "/workspace/docs/specs",
						Name:        "specs",
						Kind:        EntryKindDirectory,
						HasChildren: true,
					},
					{
						Path: "/workspace/docs/README.md",
						Name: "README.md",
						Kind: EntryKindFile,
					},
				},
			},
		},
	}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	snapshot, err := service.GetDirectoryTreeSnapshot(context.Background(), "ws-1", DirectoryTreeSnapshotInput{
		Path:          "/workspace",
		PrefetchDepth: 2,
	})
	if err != nil {
		t.Fatalf("GetDirectoryTreeSnapshot() error = %v", err)
	}

	if snapshot.Directory.PrefetchState != DirectoryTreePrefetchStatePartial {
		t.Fatalf("root prefetch state = %q, want %q", snapshot.Directory.PrefetchState, DirectoryTreePrefetchStatePartial)
	}
	if len(snapshot.Directory.Entries) != 1 {
		t.Fatalf("root entries = %#v", snapshot.Directory.Entries)
	}
	docs := snapshot.Directory.Entries[0]
	if docs.PrefetchedDirectory == nil {
		t.Fatal("expected docs directory to be prefetched")
	}
	if docs.PrefetchState != DirectoryTreePrefetchStatePartial {
		t.Fatalf("docs prefetch state = %q, want %q", docs.PrefetchState, DirectoryTreePrefetchStatePartial)
	}
	if len(docs.PrefetchedDirectory.Entries) != 2 {
		t.Fatalf("docs entries = %#v", docs.PrefetchedDirectory.Entries)
	}
	specs := docs.PrefetchedDirectory.Entries[0]
	if specs.PrefetchState != DirectoryTreePrefetchStateNotLoaded {
		t.Fatalf("specs state = %q, want %q", specs.PrefetchState, DirectoryTreePrefetchStateNotLoaded)
	}
	if specs.PrefetchReason != DirectoryTreePrefetchReasonDepthLimitReached {
		t.Fatalf("specs reason = %q, want %q", specs.PrefetchReason, DirectoryTreePrefetchReasonDepthLimitReached)
	}
}

func TestServiceGetDirectoryTreeSnapshotSkipsPolicyBlockedDirectories(t *testing.T) {
	baseAdapter := &fakeAdapter{
		directoryListingByPath: map[LogicalPath]DirectoryListing{
			"/workspace": {
				DirectoryPath: "/workspace",
				Entries: []FileEntry{
					{
						Path:        "/workspace/docs",
						Name:        "docs",
						Kind:        EntryKindDirectory,
						HasChildren: true,
					},
					{
						Path:        "/workspace/System",
						Name:        "System",
						Kind:        EntryKindDirectory,
						HasChildren: true,
					},
				},
			},
			"/workspace/docs": {
				DirectoryPath: "/workspace/docs",
				Entries: []FileEntry{
					{
						Path: "/workspace/docs/README.md",
						Name: "README.md",
						Kind: EntryKindFile,
					},
				},
			},
			"/workspace/System": {
				DirectoryPath: "/workspace/System",
				Entries: []FileEntry{
					{
						Path: "/workspace/System/private.txt",
						Name: "private.txt",
						Kind: EntryKindFile,
					},
				},
			},
		},
		listDirectoryCallsByPath: map[LogicalPath]int{},
	}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter: prefetchPolicyAdapter{
			fakeAdapter:  baseAdapter,
			blockedPaths: map[LogicalPath]struct{}{"/workspace/System": {}},
		},
	}

	snapshot, err := service.GetDirectoryTreeSnapshot(context.Background(), "ws-1", DirectoryTreeSnapshotInput{
		Path:          "/workspace",
		PrefetchDepth: 4,
	})
	if err != nil {
		t.Fatalf("GetDirectoryTreeSnapshot() error = %v", err)
	}

	docs := snapshot.Directory.Entries[0]
	if docs.PrefetchedDirectory == nil {
		t.Fatal("expected unblocked docs directory to be prefetched")
	}
	system := snapshot.Directory.Entries[1]
	if system.PrefetchedDirectory != nil {
		t.Fatalf("blocked directory was prefetched: %#v", system.PrefetchedDirectory)
	}
	if system.PrefetchState != DirectoryTreePrefetchStateNotLoaded {
		t.Fatalf("blocked directory state = %q, want %q", system.PrefetchState, DirectoryTreePrefetchStateNotLoaded)
	}
	if system.PrefetchReason != DirectoryTreePrefetchReasonDepthLimitReached {
		t.Fatalf("blocked directory reason = %q, want %q", system.PrefetchReason, DirectoryTreePrefetchReasonDepthLimitReached)
	}
	if baseAdapter.listDirectoryCallsByPath["/workspace/System"] != 0 {
		t.Fatalf("blocked directory list calls = %d, want 0", baseAdapter.listDirectoryCallsByPath["/workspace/System"])
	}
	if baseAdapter.listDirectoryCallsByPath["/workspace/docs"] == 0 {
		t.Fatal("expected unblocked docs directory to be listed")
	}
}

func TestServiceGetDirectoryTreeSnapshotMarksBudgetLimitedBranches(t *testing.T) {
	adapter := &fakeAdapter{
		directoryListingByPath: map[LogicalPath]DirectoryListing{
			"/workspace": {
				DirectoryPath: "/workspace",
				Entries: []FileEntry{
					{
						Path:        "/workspace/docs",
						Name:        "docs",
						Kind:        EntryKindDirectory,
						HasChildren: true,
					},
				},
			},
		},
		listDirectoryDelayByPath: map[LogicalPath]time.Duration{
			"/workspace/docs": 25 * time.Millisecond,
		},
	}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	snapshot, err := service.GetDirectoryTreeSnapshot(context.Background(), "ws-1", DirectoryTreeSnapshotInput{
		Path:           "/workspace",
		PrefetchBudget: 5 * time.Millisecond,
		PrefetchDepth:  3,
	})
	if err != nil {
		t.Fatalf("GetDirectoryTreeSnapshot() error = %v", err)
	}

	docs := snapshot.Directory.Entries[0]
	if docs.PrefetchState != DirectoryTreePrefetchStateNotLoaded {
		t.Fatalf("docs state = %q, want %q", docs.PrefetchState, DirectoryTreePrefetchStateNotLoaded)
	}
	if docs.PrefetchReason != DirectoryTreePrefetchReasonBudgetExhausted {
		t.Fatalf("docs reason = %q, want %q", docs.PrefetchReason, DirectoryTreePrefetchReasonBudgetExhausted)
	}
	if !snapshot.BudgetExceeded {
		t.Fatal("expected snapshot budget flag to be set")
	}
}

func TestServiceRejectsRootDelete(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	err := service.DeleteEntry(context.Background(), "ws-1", "/workspace", EntryKindDirectory)
	if !errors.Is(err, ErrRootDeleteForbidden) {
		t.Fatalf("DeleteEntry() error = %v, want %v", err, ErrRootDeleteForbidden)
	}
	if adapter.deletePath != "" {
		t.Fatalf("adapter should not be called, got path %q", adapter.deletePath)
	}
}

func TestServiceNormalizesSearchInput(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	_, err := service.Search(context.Background(), "ws-1", SearchInput{
		Query:        "  readme  ",
		Limit:        MaxSearchLimit + 20,
		IncludeKinds: []EntryKind{EntryKindFile, EntryKindFile},
	})
	if err != nil {
		t.Fatalf("Search() error = %v", err)
	}
	if adapter.searchInput.Query != "readme" {
		t.Fatalf("query = %q", adapter.searchInput.Query)
	}
	if adapter.searchInput.Limit != MaxSearchLimit {
		t.Fatalf("limit = %d, want %d", adapter.searchInput.Limit, MaxSearchLimit)
	}
	if len(adapter.searchInput.IncludeKinds) != 1 || adapter.searchInput.IncludeKinds[0] != EntryKindFile {
		t.Fatalf("include kinds = %#v", adapter.searchInput.IncludeKinds)
	}
}

func TestServiceEmptySearchDoesNotCallAdapter(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	result, err := service.Search(context.Background(), "ws-1", SearchInput{Query: "  "})
	if err != nil {
		t.Fatalf("Search() error = %v", err)
	}
	if len(result.Entries) != 0 {
		t.Fatalf("entries = %#v, want empty", result.Entries)
	}
	if adapter.searchInput.Limit != 0 {
		t.Fatalf("adapter should not be called, got input %#v", adapter.searchInput)
	}
}

func TestServiceUploadFilesNormalizesInput(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	result, err := service.UploadFiles(context.Background(), "ws-1", UploadInput{
		Overwrite:           true,
		SourcePaths:         []string{" /tmp/readme.md ", "", "/tmp/notes.txt"},
		TargetDirectoryPath: "docs/../docs",
	})
	if err != nil {
		t.Fatalf("UploadFiles() error = %v", err)
	}
	if adapter.uploadDir != "/workspace/docs" {
		t.Fatalf("upload dir = %q", adapter.uploadDir)
	}
	if len(adapter.uploadPaths) != 2 || adapter.uploadPaths[0] != "/tmp/readme.md" || adapter.uploadPaths[1] != "/tmp/notes.txt" {
		t.Fatalf("upload paths = %#v", adapter.uploadPaths)
	}
	if !adapter.overwrite {
		t.Fatal("overwrite should be forwarded")
	}
	if result.WorkspaceID != "ws-1" || result.TargetDirectoryPath != "/workspace/docs" || len(result.Entries) != 1 {
		t.Fatalf("result = %#v", result)
	}
}

func TestServiceUploadFilesRejectsEmptySourcePaths(t *testing.T) {
	adapter := &fakeAdapter{}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	_, err := service.UploadFiles(context.Background(), "ws-1", UploadInput{
		SourcePaths:         []string{"", "   "},
		TargetDirectoryPath: "/workspace",
	})
	if !errors.Is(err, ErrInvalidUploadSource) {
		t.Fatalf("UploadFiles() error = %v, want %v", err, ErrInvalidUploadSource)
	}
	if adapter.uploadDir != "" {
		t.Fatalf("adapter should not be called, got dir %q", adapter.uploadDir)
	}
}

func TestServicePreflightUploadFilesReturnsConflicts(t *testing.T) {
	adapter := &fakeAdapter{
		conflicts: []UploadConflict{
			{
				DestinationKind: EntryKindFile,
				DestinationPath: "/workspace/docs/readme.md",
				Name:            "readme.md",
				SourcePath:      "/tmp/readme.md",
			},
		},
	}
	service := Service{
		Resolver: fakeResolver{root: WorkspaceRoot{LogicalRoot: "/workspace", PhysicalRoot: "/tmp/workspace"}},
		Adapter:  adapter,
	}

	result, err := service.PreflightUploadFiles(context.Background(), "ws-1", PreflightUploadInput{
		SourcePaths:         []string{"/tmp/readme.md"},
		TargetDirectoryPath: "/workspace/docs",
	})
	if err != nil {
		t.Fatalf("PreflightUploadFiles() error = %v", err)
	}
	if result.TargetDirectoryPath != "/workspace/docs" || len(result.Conflicts) != 1 {
		t.Fatalf("result = %#v", result)
	}
}
