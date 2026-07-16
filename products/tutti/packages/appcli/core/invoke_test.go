package core

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestInvokeHTTPPostsEnvelope(t *testing.T) {
	var envelope map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/tutti/cli/run" {
			t.Fatalf("request = %s %s", r.Method, r.URL.Path)
		}
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("decode envelope: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"kind":"json","value":{"ok":true}}`))
	}))
	defer server.Close()

	output, err := InvokeHTTP(context.Background(), HTTPInvokeRequest{
		BaseURL: server.URL,
		AppID:   "automation-app",
		Scope:   "automation",
		Command: Command{
			Capability: Capability{ID: "app.automation-app.automation.run"},
			Manifest: ManifestCommand{
				Path:    []string{"run"},
				Handler: ManifestCommandHandler{Kind: "http", Method: "POST", Path: "/tutti/cli/run"},
			},
			Timeout: time.Second,
		},
		WorkspaceID: "ws-1",
		Input:       map[string]any{"name": "daily"},
		OutputMode:  OutputModeJSON,
		Context:     InvokeContext{Source: "cli", ParentCommandID: "parent"},
	})
	if err != nil {
		t.Fatalf("InvokeHTTP() error = %v", err)
	}
	if output.Kind != OutputModeJSON || output.Value["ok"] != true {
		t.Fatalf("output = %#v", output)
	}
	if envelope["schemaVersion"] != InvokeSchemaVersion || envelope["workspaceId"] != "ws-1" {
		t.Fatalf("envelope = %#v", envelope)
	}
	contextValue := envelope["context"].(map[string]any)
	if contextValue["source"] != "cli" || contextValue["parentCommandId"] != "parent" {
		t.Fatalf("envelope context = %#v", contextValue)
	}
}
