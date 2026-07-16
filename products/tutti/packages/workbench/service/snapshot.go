package workbenchservice

import "encoding/json"

type StoredSnapshot struct {
	WorkspaceID   string
	SchemaVersion int
	JSON          json.RawMessage
}
