package workspaceissues

import (
	"encoding/base64"
	"encoding/json"
	"strings"
)

func EncodeIssueListCursorToken(cursor *IssueListCursor) string {
	if cursor == nil || cursor.ID == 0 {
		return ""
	}

	return encodePageToken(cursor)
}

func DecodeIssueListCursorToken(token string) (*IssueListCursor, error) {
	token = strings.TrimSpace(token)
	if token == "" {
		return nil, nil
	}

	var cursor IssueListCursor
	if err := decodePageToken(token, &cursor); err != nil {
		return nil, err
	}
	if cursor.ID == 0 {
		return nil, ErrInvalidArgument
	}
	return &cursor, nil
}

func EncodeTaskListCursorToken(cursor *TaskListCursor) string {
	if cursor == nil || cursor.ID == 0 {
		return ""
	}

	return encodePageToken(cursor)
}

func DecodeTaskListCursorToken(token string) (*TaskListCursor, error) {
	token = strings.TrimSpace(token)
	if token == "" {
		return nil, nil
	}

	var cursor TaskListCursor
	if err := decodePageToken(token, &cursor); err != nil {
		return nil, err
	}
	if cursor.ID == 0 {
		return nil, ErrInvalidArgument
	}
	return &cursor, nil
}

func encodePageToken(value any) string {
	data, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	return base64.RawURLEncoding.EncodeToString(data)
}

func decodePageToken(token string, target any) error {
	data, err := base64.RawURLEncoding.DecodeString(token)
	if err != nil {
		return ErrInvalidArgument
	}
	if err := json.Unmarshal(data, target); err != nil {
		return ErrInvalidArgument
	}
	return nil
}
