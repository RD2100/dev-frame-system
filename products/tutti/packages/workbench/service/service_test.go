package workbenchservice

import (
	"context"
	"errors"
	"testing"
)

type stubStore struct {
	getSnapshotFn func(context.Context, string) (StoredSnapshot, error)
	putSnapshotFn func(context.Context, StoredSnapshot) error
}

func (s stubStore) GetSnapshot(ctx context.Context, workspaceID string) (StoredSnapshot, error) {
	if s.getSnapshotFn == nil {
		return StoredSnapshot{}, nil
	}

	return s.getSnapshotFn(ctx, workspaceID)
}

func (s stubStore) PutSnapshot(ctx context.Context, snapshot StoredSnapshot) error {
	if s.putSnapshotFn == nil {
		return nil
	}

	return s.putSnapshotFn(ctx, snapshot)
}

func TestServiceGetSnapshotReturnsDefaultWhenStoreMisses(t *testing.T) {
	t.Parallel()

	service := Service{
		Store: stubStore{
			getSnapshotFn: func(context.Context, string) (StoredSnapshot, error) {
				return StoredSnapshot{}, ErrWorkbenchSnapshotNotFound
			},
		},
	}

	snapshot, err := service.GetSnapshot(context.Background(), "workspace-1")
	if err != nil {
		t.Fatalf("GetSnapshot() error = %v", err)
	}
	if snapshot.WorkspaceID != "workspace-1" {
		t.Fatalf("WorkspaceID = %q, want workspace-1", snapshot.WorkspaceID)
	}
	if snapshot.SchemaVersion != workbenchSnapshotContractSchemaVersion {
		t.Fatalf("SchemaVersion = %d, want %d", snapshot.SchemaVersion, workbenchSnapshotContractSchemaVersion)
	}
	if string(snapshot.JSON) != string(defaultWorkbenchSnapshotJSON()) {
		t.Fatalf("JSON = %s, want %s", snapshot.JSON, defaultWorkbenchSnapshotJSON())
	}
}

func TestServicePutSnapshotPersistsCanonicalJSON(t *testing.T) {
	t.Parallel()

	var stored StoredSnapshot
	service := Service{
		Store: stubStore{
			putSnapshotFn: func(_ context.Context, snapshot StoredSnapshot) error {
				stored = snapshot
				return nil
			},
		},
	}

	input := canonicalizationWorkbenchSnapshotFixture()
	snapshot, err := service.PutSnapshot(context.Background(), "workspace-1", input)
	if err != nil {
		t.Fatalf("PutSnapshot() error = %v", err)
	}
	if snapshot.WorkspaceID != "workspace-1" {
		t.Fatalf("WorkspaceID = %q, want workspace-1", snapshot.WorkspaceID)
	}
	if string(snapshot.JSON) != string(stored.JSON) {
		t.Fatalf("stored JSON = %s, want %s", stored.JSON, snapshot.JSON)
	}
}

func TestServicePutSnapshotWrapsInvalidSnapshotError(t *testing.T) {
	t.Parallel()

	service := Service{
		Store: stubStore{},
	}

	_, err := service.PutSnapshot(context.Background(), "workspace-1", WorkbenchSnapshot{})
	if !errors.Is(err, ErrInvalidWorkbenchSnapshot) {
		t.Fatalf("PutSnapshot() error = %v, want ErrInvalidWorkbenchSnapshot", err)
	}
}
