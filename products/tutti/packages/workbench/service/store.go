package workbenchservice

import "context"

type Store interface {
	GetSnapshot(context.Context, string) (StoredSnapshot, error)
	PutSnapshot(context.Context, StoredSnapshot) error
}
