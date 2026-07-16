package workbenchservice

import (
	"encoding/json"
	"fmt"
)

func defaultWorkbenchSnapshotJSON() json.RawMessage {
	return json.RawMessage(
		fmt.Sprintf(
			`{"schemaVersion":%d,"nodes":[],"nodeStack":[],"activeNodeId":null}`,
			workbenchSnapshotContractSchemaVersion,
		),
	)
}
