package core

import (
	"errors"
	"testing"
)

func TestValidateCommandOutputFillsDeclaredTableColumns(t *testing.T) {
	output, err := ValidateCommandOutput(CapabilityOutput{
		DefaultMode: OutputModeTable,
		JSON:        true,
		Table:       &TableOutput{Columns: []TableColumn{{Key: "id", Label: "ID"}}},
	}, CommandOutput{
		Kind: OutputModeTable,
		Rows: []map[string]any{{"id": "job-1"}},
	})
	if err != nil {
		t.Fatalf("ValidateCommandOutput() error = %v", err)
	}
	if len(output.Columns) != 1 || output.Columns[0].Key != "id" {
		t.Fatalf("output = %#v", output)
	}
}

func TestValidateCommandOutputRejectsUndeclaredJSON(t *testing.T) {
	_, err := ValidateCommandOutput(CapabilityOutput{
		DefaultMode: OutputModeTable,
		Table:       &TableOutput{Columns: []TableColumn{{Key: "id", Label: "ID"}}},
	}, CommandOutput{Kind: OutputModeJSON, Value: map[string]any{"ok": true}})
	if !errors.Is(err, ErrHandlerBadResponse) {
		t.Fatalf("ValidateCommandOutput() error = %v, want ErrHandlerBadResponse", err)
	}
}
