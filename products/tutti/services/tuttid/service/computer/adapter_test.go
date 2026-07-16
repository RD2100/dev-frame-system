package computer

import "testing"

func TestSplitKeySpec(t *testing.T) {
	tests := []struct {
		in   string
		want []string
	}{
		{"cmd+space", []string{"cmd", "space"}},
		{"cmd+c", []string{"cmd", "c"}},
		{"return", []string{"return"}},
		{"Command+Shift+4", []string{"cmd", "shift", "4"}},
	}
	for _, tc := range tests {
		got := splitKeySpec(tc.in)
		if len(got) != len(tc.want) {
			t.Fatalf("splitKeySpec(%q) = %#v, want %#v", tc.in, got, tc.want)
		}
		for i := range got {
			if got[i] != tc.want[i] {
				t.Fatalf("splitKeySpec(%q)[%d] = %q, want %q", tc.in, i, got[i], tc.want[i])
			}
		}
	}
}

func TestDecodeStructuredPayload(t *testing.T) {
	payload, err := decodeStructuredPayload[windowStatePayload](`{"screenshot_file_path":"/tmp/test.png"}`)
	if err != nil {
		t.Fatalf("decodeStructuredPayload: %v", err)
	}
	if payload.ScreenshotFilePath != "/tmp/test.png" {
		t.Fatalf("ScreenshotFilePath = %q", payload.ScreenshotFilePath)
	}
}

func TestParseAccessibilityTreeWindows(t *testing.T) {
	text := "Windows:\n- Cua Driver (pid 59271) (no title) [window_id: 22516]\n- Warp (pid 40206) \"Title\" [window_id: 6392]\n"
	windows, err := parseAccessibilityTreeWindows(text)
	if err != nil {
		t.Fatalf("parseAccessibilityTreeWindows: %v", err)
	}
	if len(windows) != 2 {
		t.Fatalf("windows = %d, want 2", len(windows))
	}
	if windows[0].AppName != "Warp" || windows[0].PID != 40206 || windows[0].WindowID != 6392 {
		t.Fatalf("frontmost window = %+v, want Warp 40206/6392", windows[0])
	}
}

func TestNumericArg(t *testing.T) {
	value, ok := numericArg(map[string]any{"x": "120"}, "x")
	if !ok || value != 120 {
		t.Fatalf("numericArg = (%v, %v)", value, ok)
	}
}
