package workspace

import (
	"encoding/json"
	"time"
)

type Summary struct {
	ID           string
	Name         string
	LastOpenedAt *time.Time
}

type WorkbenchSnapshot struct {
	WorkspaceID   string
	SchemaVersion int
	JSON          json.RawMessage
}
