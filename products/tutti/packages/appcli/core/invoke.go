package core

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const InvokeSchemaVersion = "tutti.app.cli.invoke.v1"

type InvokeContext struct {
	Source          string
	ParentCommandID string
}

type HTTPInvokeRequest struct {
	BaseURL     string
	Command     Command
	AppID       string
	Scope       string
	WorkspaceID string
	Input       map[string]any
	OutputMode  OutputMode
	Context     InvokeContext
	HTTPClient  *http.Client
}

type InvokeEnvelope struct {
	SchemaVersion string                `json:"schemaVersion"`
	CommandID     string                `json:"commandId"`
	AppID         string                `json:"appId"`
	Scope         string                `json:"scope"`
	Path          []string              `json:"path"`
	WorkspaceID   string                `json:"workspaceId"`
	Input         map[string]any        `json:"input"`
	OutputMode    OutputMode            `json:"outputMode"`
	Context       InvokeEnvelopeContext `json:"context"`
}

type InvokeEnvelopeContext struct {
	Source          string  `json:"source"`
	ParentCommandID *string `json:"parentCommandId"`
}

func BuildInvokeEnvelope(request HTTPInvokeRequest) InvokeEnvelope {
	return InvokeEnvelope{
		SchemaVersion: InvokeSchemaVersion,
		CommandID:     request.Command.Capability.ID,
		AppID:         strings.TrimSpace(request.AppID),
		Scope:         strings.TrimSpace(request.Scope),
		Path:          append([]string(nil), request.Command.Manifest.Path...),
		WorkspaceID:   strings.TrimSpace(request.WorkspaceID),
		Input:         request.Input,
		OutputMode:    request.OutputMode,
		Context: InvokeEnvelopeContext{
			Source:          firstNonEmpty(request.Context.Source, "cli"),
			ParentCommandID: nullableString(request.Context.ParentCommandID),
		},
	}
}

func InvokeHTTP(ctx context.Context, request HTTPInvokeRequest) (CommandOutput, error) {
	endpoint, err := url.JoinPath(strings.TrimRight(strings.TrimSpace(request.BaseURL), "/"), request.Command.Manifest.Handler.Path)
	if err != nil {
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", err)
	}
	body, err := json.Marshal(BuildInvokeEnvelope(request))
	if err != nil {
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", err)
	}
	timeout := request.Command.Timeout
	if timeout <= 0 {
		timeout = time.Duration(DefaultTimeoutMs) * time.Millisecond
	}
	requestCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	httpRequest, err := http.NewRequestWithContext(requestCtx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", err)
	}
	httpRequest.Header.Set("Accept", "application/json")
	httpRequest.Header.Set("Content-Type", "application/json")

	response, err := httpClient(request.HTTPClient).Do(httpRequest)
	if err != nil {
		if errors.Is(requestCtx.Err(), context.DeadlineExceeded) {
			return CommandOutput{}, invokeError(ErrServiceUnavailable, "app_cli_handler_timeout", err)
		}
		if isConnectionUnavailable(err) {
			return CommandOutput{}, invokeError(ErrServiceUnavailable, "app_cli_runtime_unavailable", err)
		}
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", err)
	}
	defer response.Body.Close()
	content, err := io.ReadAll(io.LimitReader(response.Body, 1024*1024))
	if err != nil {
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", err)
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		if validAppErrorBody(content) {
			return CommandOutput{}, invokeError(ErrHandlerFailed, "app_cli_handler_failed", errors.New(appErrorMessage(content)))
		}
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", fmt.Errorf("app cli handler returned %s", response.Status))
	}
	output, err := DecodeCommandOutput(content)
	if err != nil {
		return CommandOutput{}, invokeError(ErrHandlerBadResponse, "app_cli_handler_bad_response", err)
	}
	return output, nil
}

func httpClient(client *http.Client) *http.Client {
	if client != nil {
		return client
	}
	return &http.Client{Timeout: MaxTimeoutMs*time.Millisecond + 30*time.Second}
}

func nullableString(value string) *string {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return &value
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func isConnectionUnavailable(err error) bool {
	var netErr net.Error
	if errors.As(err, &netErr) {
		return true
	}
	return strings.Contains(strings.ToLower(err.Error()), "connection refused")
}

func validAppErrorBody(content []byte) bool {
	var body struct {
		Error *struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.Unmarshal(content, &body); err != nil {
		return false
	}
	return body.Error != nil && strings.TrimSpace(body.Error.Code) != "" && strings.TrimSpace(body.Error.Message) != ""
}

func appErrorMessage(content []byte) string {
	var body struct {
		Error struct {
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.Unmarshal(content, &body); err == nil && strings.TrimSpace(body.Error.Message) != "" {
		return strings.TrimSpace(body.Error.Message)
	}
	return "app cli handler failed"
}
