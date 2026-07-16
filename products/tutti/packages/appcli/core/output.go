package core

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
)

func DecodeCommandOutput(content []byte) (CommandOutput, error) {
	var raw struct {
		Kind    OutputMode       `json:"kind"`
		Columns []TableColumn    `json:"columns"`
		Rows    []map[string]any `json:"rows"`
		Value   map[string]any   `json:"value"`
		Text    string           `json:"text"`
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	if err := decoder.Decode(&raw); err != nil {
		return CommandOutput{}, err
	}
	if raw.Kind == "" {
		return CommandOutput{}, errors.New("cli command output kind is required")
	}
	return CommandOutput{
		Kind:    raw.Kind,
		Columns: raw.Columns,
		Rows:    raw.Rows,
		Value:   raw.Value,
		Text:    raw.Text,
	}, nil
}

func ValidateCommandOutput(contract CapabilityOutput, output CommandOutput) (CommandOutput, error) {
	switch output.Kind {
	case OutputModeJSON:
		if !contract.JSON {
			return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", errors.New("json output is not declared"))
		}
	case OutputModeTable:
		if contract.Table == nil {
			return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", errors.New("table output is not declared"))
		}
		columns, err := normalizeOutputColumns(contract.Table.Columns, output.Columns)
		if err != nil {
			return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", err)
		}
		output.Columns = columns
	default:
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", fmt.Errorf("unsupported output kind %q", output.Kind))
	}
	return output, nil
}

func normalizeOutputColumns(contract []TableColumn, actual []TableColumn) ([]TableColumn, error) {
	if len(actual) == 0 {
		return append([]TableColumn(nil), contract...), nil
	}
	contractByKey := map[string]TableColumn{}
	for _, column := range contract {
		contractByKey[column.Key] = column
	}
	result := make([]TableColumn, 0, len(actual))
	for _, column := range actual {
		expected, ok := contractByKey[column.Key]
		if !ok || expected.Label != column.Label {
			return nil, fmt.Errorf("table output column %q is not declared", column.Key)
		}
		result = append(result, column)
	}
	return result, nil
}
