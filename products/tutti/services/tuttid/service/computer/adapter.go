package computer

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

type windowRecord struct {
	PID        int    `json:"pid"`
	WindowID   int    `json:"window_id"`
	ZIndex     int    `json:"z_index"`
	AppName    string `json:"app_name"`
	Title      string `json:"title"`
	IsOnScreen bool   `json:"is_on_screen"`
}

type windowStatePayload struct {
	ScreenshotFilePath string `json:"screenshot_file_path"`
}

var accessibilityWindowLinePattern = regexp.MustCompile(`^- (.+) \(pid (\d+)\)(?: "(.*)"| \(no title\)) \[window_id: (\d+)\]$`)

// adaptToolCall translates legacy tutti computer CLI tool names and arguments
// to the cua-driver 0.5.x MCP API (pid/window_id scoped actions).
func (s *computerSession) adaptToolCall(ctx context.Context, tool string, args map[string]any) (ToolResult, error) {
	switch tool {
	case "screenshot":
		return s.adaptScreenshot(ctx)
	case "left_click":
		return s.adaptPointerAction(ctx, "click", args)
	case "double_click", "right_click":
		return s.adaptPointerAction(ctx, tool, args)
	case "press_key":
		return s.adaptPressKey(ctx, args)
	case "type_text", "scroll":
		return s.adaptPIDRequiredTool(ctx, tool, args)
	default:
		return s.callTool(ctx, tool, args)
	}
}

func (s *computerSession) adaptScreenshot(ctx context.Context) (ToolResult, error) {
	target, err := s.resolveFrontmostWindow(ctx)
	if err != nil {
		return ToolResult{}, err
	}

	file, err := os.CreateTemp("", "tutti-computer-*.png")
	if err != nil {
		return ToolResult{}, err
	}
	path := file.Name()
	_ = file.Close()

	raw, err := s.callTool(ctx, "get_window_state", map[string]any{
		"pid":                 target.PID,
		"window_id":           target.WindowID,
		"capture_mode":        "vision",
		"screenshot_out_file": path,
	})
	if err != nil {
		_ = os.Remove(path)
		return ToolResult{}, err
	}
	if _, statErr := os.Stat(path); statErr != nil {
		_ = os.Remove(path)
		return ToolResult{}, fmt.Errorf("screenshot file missing after capture: %w (tool output: %s)", statErr, truncateForError(raw.Text))
	}

	return ToolResult{Text: fmt.Sprintf("Screenshot saved to %s", path)}, nil
}

func (s *computerSession) adaptPointerAction(ctx context.Context, tool string, args map[string]any) (ToolResult, error) {
	target, err := s.resolveFrontmostWindow(ctx)
	if err != nil {
		return ToolResult{}, err
	}

	out := map[string]any{
		"pid":       target.PID,
		"window_id": target.WindowID,
	}
	if x, ok := numericArg(args, "x"); ok {
		out["x"] = x
	}
	if y, ok := numericArg(args, "y"); ok {
		out["y"] = y
	}
	return s.callTool(ctx, tool, out)
}

func (s *computerSession) adaptPressKey(ctx context.Context, args map[string]any) (ToolResult, error) {
	keySpec, ok := stringArg(args, "key")
	if !ok || strings.TrimSpace(keySpec) == "" {
		return ToolResult{}, fmt.Errorf("missing required string field: key")
	}

	target, err := s.resolveFrontmostWindow(ctx)
	if err != nil {
		return ToolResult{}, err
	}

	parts := splitKeySpec(keySpec)
	if len(parts) > 1 {
		return s.callTool(ctx, "hotkey", map[string]any{
			"pid":  target.PID,
			"keys": parts,
		})
	}

	return s.callTool(ctx, "press_key", map[string]any{
		"pid": target.PID,
		"key": parts[0],
	})
}

func (s *computerSession) adaptPIDRequiredTool(ctx context.Context, tool string, args map[string]any) (ToolResult, error) {
	target, err := s.resolveFrontmostWindow(ctx)
	if err != nil {
		return ToolResult{}, err
	}

	out := map[string]any{"pid": target.PID}
	for key, value := range args {
		switch key {
		case "x", "y":
			continue
		case "amount":
			if amount, ok := numericArg(args, "amount"); ok {
				out["amount"] = int(amount)
			}
		default:
			out[key] = value
		}
	}
	if tool == "scroll" {
		if _, ok := out["amount"]; !ok {
			out["amount"] = 3
		}
	}
	return s.callTool(ctx, tool, out)
}

func (s *computerSession) resolveFrontmostWindow(ctx context.Context) (windowRecord, error) {
	raw, err := s.callTool(ctx, "get_accessibility_tree", nil)
	if err != nil {
		return windowRecord{}, err
	}

	windows, err := parseAccessibilityTreeWindows(raw.Text)
	if err != nil {
		return windowRecord{}, err
	}

	return windows[0], nil
}

func parseAccessibilityTreeWindows(text string) ([]windowRecord, error) {
	lines := strings.Split(text, "\n")
	windows := make([]windowRecord, 0, len(lines))
	for _, line := range lines {
		line = strings.TrimSpace(line)
		matches := accessibilityWindowLinePattern.FindStringSubmatch(line)
		if len(matches) != 5 {
			continue
		}
		pid, err := strconv.Atoi(matches[2])
		if err != nil {
			continue
		}
		windowID, err := strconv.Atoi(matches[4])
		if err != nil {
			continue
		}
		windows = append(windows, windowRecord{
			AppName:  matches[1],
			PID:      pid,
			WindowID: windowID,
			Title:    matches[3],
		})
	}
	if len(windows) == 0 {
		return nil, fmt.Errorf("no visible windows found in accessibility tree")
	}

	sort.SliceStable(windows, func(i, j int) bool {
		return windowAutomationPriority(windows[i]) > windowAutomationPriority(windows[j])
	})
	return windows, nil
}

func windowAutomationPriority(window windowRecord) int {
	name := strings.ToLower(strings.TrimSpace(window.AppName))
	switch {
	case name == "cua driver":
		return 0
	case strings.Contains(name, "tutti"):
		return 10
	case strings.TrimSpace(window.Title) == "":
		return 20
	default:
		return 100
	}
}

func decodeStructuredPayload[T any](text string) (T, error) {
	var zero T
	text = strings.TrimSpace(text)
	if text == "" {
		return zero, fmt.Errorf("empty structured tool result")
	}
	if err := json.Unmarshal([]byte(text), &zero); err == nil {
		return zero, nil
	}

	start := strings.Index(text, "{")
	end := strings.LastIndex(text, "}")
	if start >= 0 && end > start {
		if err := json.Unmarshal([]byte(text[start:end+1]), &zero); err == nil {
			return zero, nil
		}
	}
	return zero, fmt.Errorf("decode structured tool result: %s", truncateForError(text))
}

func splitKeySpec(spec string) []string {
	parts := strings.Split(spec, "+")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(strings.ToLower(part))
		switch part {
		case "command":
			part = "cmd"
		case "control":
			part = "ctrl"
		case "option", "alt":
			part = "option"
		}
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func stringArg(args map[string]any, key string) (string, bool) {
	value, ok := args[key]
	if !ok || value == nil {
		return "", false
	}
	switch typed := value.(type) {
	case string:
		return typed, true
	default:
		return fmt.Sprint(typed), true
	}
}

func numericArg(args map[string]any, key string) (float64, bool) {
	value, ok := args[key]
	if !ok || value == nil {
		return 0, false
	}
	switch typed := value.(type) {
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case json.Number:
		parsed, err := typed.Float64()
		return parsed, err == nil
	case string:
		parsed, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		return parsed, err == nil
	default:
		return 0, false
	}
}

func truncateForError(text string) string {
	text = strings.TrimSpace(text)
	if len(text) <= 240 {
		return text
	}
	return text[:240] + "..."
}
