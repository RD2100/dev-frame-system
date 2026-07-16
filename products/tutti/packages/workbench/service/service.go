package workbenchservice

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

type Service struct {
	Store Store
}

func (s Service) GetSnapshot(ctx context.Context, workspaceID string) (StoredSnapshot, error) {
	if s.Store == nil {
		return StoredSnapshot{}, ErrWorkbenchStoreNotConfigured
	}

	workspaceID = strings.TrimSpace(workspaceID)
	if workspaceID == "" {
		return StoredSnapshot{}, errors.New("workspace id is required")
	}

	snapshot, err := s.Store.GetSnapshot(ctx, workspaceID)
	if errors.Is(err, ErrWorkbenchSnapshotNotFound) {
		return StoredSnapshot{
			WorkspaceID:   workspaceID,
			SchemaVersion: workbenchSnapshotContractSchemaVersion,
			JSON:          defaultWorkbenchSnapshotJSON(),
		}, nil
	}
	if err != nil {
		return StoredSnapshot{}, err
	}

	return snapshot, nil
}

func (s Service) PutSnapshot(
	ctx context.Context,
	workspaceID string,
	snapshotInput WorkbenchSnapshot,
) (StoredSnapshot, error) {
	if s.Store == nil {
		return StoredSnapshot{}, ErrWorkbenchStoreNotConfigured
	}

	workspaceID = strings.TrimSpace(workspaceID)
	if workspaceID == "" {
		return StoredSnapshot{}, errors.New("workspace id is required")
	}

	normalizedJSON, schemaVersion, err := normalizeWorkbenchSnapshot(snapshotInput)
	if err != nil {
		return StoredSnapshot{}, fmt.Errorf("%w: %v", ErrInvalidWorkbenchSnapshot, err)
	}

	snapshot := StoredSnapshot{
		WorkspaceID:   workspaceID,
		SchemaVersion: schemaVersion,
		JSON:          normalizedJSON,
	}
	if err := s.Store.PutSnapshot(ctx, snapshot); err != nil {
		return StoredSnapshot{}, err
	}

	return snapshot, nil
}
