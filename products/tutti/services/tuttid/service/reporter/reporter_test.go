package reporter

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	tuttitypes "github.com/tutti-os/tutti/services/tuttid/types"
	sdk "github.com/volcengine/datarangers-sdk-go"
)

func TestNewReporterUsesNoopWhenDisabled(t *testing.T) {
	got, err := New(Config{
		Analytics: tuttitypes.AnalyticsConfig{
			Disabled: true,
		},
		StateDir: t.TempDir(),
	})
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	if _, ok := got.(*NoopReporter); !ok {
		t.Fatalf("reporter = %T, want *NoopReporter", got)
	}
}

func TestNewReporterUsesNoopWhenConfigIncomplete(t *testing.T) {
	cases := []tuttitypes.AnalyticsConfig{
		{AppID: 0, AppKey: "key", ChannelDomain: "https://example.test"},
		{AppID: 1, AppKey: "", ChannelDomain: "https://example.test"},
		{AppID: 1, AppKey: "key", ChannelDomain: ""},
	}

	for _, analytics := range cases {
		got, err := New(Config{Analytics: analytics, StateDir: t.TempDir()})
		if err != nil {
			t.Fatalf("New() error = %v", err)
		}
		if _, ok := got.(*NoopReporter); !ok {
			t.Fatalf("reporter = %T, want *NoopReporter", got)
		}
	}
}

func TestNewReporterUsesDebugOnlyReporterWhenDebugEnabled(t *testing.T) {
	debugPublisher := &fakeDebugPublisher{}
	got, err := New(Config{
		Analytics: tuttitypes.AnalyticsConfig{
			Debug:         true,
			AppID:         1,
			AppKey:        "key",
			ChannelDomain: "https://example.test",
			AppVersion:    "1.2.3",
		},
		DebugPublisher: debugPublisher,
		StateDir:       t.TempDir(),
	})
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	if _, ok := got.(*DebugReporter); !ok {
		t.Fatalf("reporter = %T, want *DebugReporter", got)
	}

	got.Track(context.Background(), Event{
		Name:     "workspace.opened",
		ClientTS: 1749124800000,
		Params: map[string]any{
			"source":     "dashboard",
			"device_id":  "spoofed",
			"session_id": "spoofed",
		},
	})

	if len(debugPublisher.events) != 1 {
		t.Fatalf("debug events = %d, want 1", len(debugPublisher.events))
	}
	event := debugPublisher.events[0]
	if event.Name != "workspace.opened" {
		t.Fatalf("debug event name = %q, want workspace.opened", event.Name)
	}
	if event.ClientTS != 1749124800000 {
		t.Fatalf("debug event client ts = %d, want 1749124800000", event.ClientTS)
	}
	if event.Params["source"] != "dashboard" {
		t.Fatalf("debug source param = %v, want dashboard", event.Params["source"])
	}
	if event.Params["device_id"] == "" || event.Params["device_id"] == "spoofed" {
		t.Fatalf("debug device_id = %v, want daemon-owned value", event.Params["device_id"])
	}
	if event.Params["session_id"] == "" || event.Params["session_id"] == "spoofed" {
		t.Fatalf("debug session_id = %v, want daemon-owned value", event.Params["session_id"])
	}
	if event.Params["app_version"] != "1.2.3" {
		t.Fatalf("debug app_version = %v, want 1.2.3", event.Params["app_version"])
	}
	if event.Params["os"] == "" {
		t.Fatalf("debug os = %v, want daemon-owned value", event.Params["os"])
	}
}

func TestNoopReporterAcceptsEventsAndCloses(t *testing.T) {
	reporter := &NoopReporter{}
	reporter.Track(context.Background(), Event{Name: "workspace.opened", ClientTS: 1})
	if err := reporter.Close(); err != nil {
		t.Fatalf("Close() error = %v", err)
	}
}

type fakeTeaSDK struct {
	initCalls  int
	initConfig teaSDKConfig
	sends      []fakeTeaSend
	closed     bool
}

type fakeDebugPublisher struct {
	events []DebugEvent
}

func (f *fakeDebugPublisher) PublishAnalyticsDebugEvents(_ context.Context, events []DebugEvent) {
	f.events = append(f.events, events...)
}

type fakeTeaSend struct {
	appID  int64
	uuid   string
	events []teaSDKEvent
	common map[string]any
}

func (f *fakeTeaSDK) Init(config teaSDKConfig) error {
	f.initCalls++
	f.initConfig = config
	return nil
}

func (f *fakeTeaSDK) Send(appID int64, uuid string, events []teaSDKEvent, common map[string]any) error {
	f.sends = append(f.sends, fakeTeaSend{
		appID:  appID,
		uuid:   uuid,
		events: events,
		common: common,
	})
	return nil
}

func (f *fakeTeaSDK) Close() error {
	f.closed = true
	return nil
}

func TestTeaReporterInjectsDaemonOwnedCommonParams(t *testing.T) {
	sdk := &fakeTeaSDK{}
	debugPublisher := &fakeDebugPublisher{}
	stateDir := t.TempDir()
	reporter, err := newTeaReporterWithSDK(Config{
		Analytics: tuttitypes.AnalyticsConfig{
			AppID:         20004092,
			AppKey:        "app-key",
			Channel:       "sg",
			ChannelDomain: "https://example.test",
			AppVersion:    "0.0.0",
		},
		DebugPublisher: debugPublisher,
		StateDir:       stateDir,
	}, sdk)
	if err != nil {
		t.Fatalf("newTeaReporterWithSDK() error = %v", err)
	}
	if sdk.initCalls != 1 {
		t.Fatalf("Init calls = %d, want 1", sdk.initCalls)
	}
	if sdk.initConfig.AppID != 20004092 {
		t.Fatalf("Init AppID = %d, want 20004092", sdk.initConfig.AppID)
	}
	if sdk.initConfig.AppKey != "app-key" {
		t.Fatalf("Init AppKey = %q, want app-key", sdk.initConfig.AppKey)
	}
	if sdk.initConfig.ChannelDomain != "https://example.test" {
		t.Fatalf("Init ChannelDomain = %q, want https://example.test", sdk.initConfig.ChannelDomain)
	}
	if sdk.initConfig.StateDir != stateDir {
		t.Fatalf("Init StateDir = %q, want %q", sdk.initConfig.StateDir, stateDir)
	}

	reporter.Track(context.Background(), Event{
		Name:     "workspace.opened",
		ClientTS: 1749124800000,
		Params: map[string]any{
			"source":     "dashboard",
			"device_id":  "spoofed",
			"session_id": "spoofed",
		},
	})

	if len(sdk.sends) != 1 {
		t.Fatalf("Send calls = %d, want 1", len(sdk.sends))
	}
	send := sdk.sends[0]
	if send.appID != 20004092 {
		t.Fatalf("Send appID = %d, want 20004092", send.appID)
	}
	if send.uuid == "" {
		t.Fatal("Send uuid is empty")
	}
	if send.uuid == "spoofed" {
		t.Fatal("Send uuid used renderer-supplied spoofed value")
	}
	deviceIDFile, err := os.ReadFile(filepath.Join(stateDir, "device_id"))
	if err != nil {
		t.Fatalf("read persisted device_id error = %v", err)
	}
	if got := strings.TrimSpace(string(deviceIDFile)); got != send.uuid {
		t.Fatalf("persisted device_id = %q, want send uuid %q", got, send.uuid)
	}

	deviceID, ok := send.common["device_id"].(string)
	if !ok || deviceID == "" {
		t.Fatalf("common device_id = %v, want non-empty string", send.common["device_id"])
	}
	if deviceID != send.uuid {
		t.Fatalf("common device_id = %q, want send uuid %q", deviceID, send.uuid)
	}
	sessionID, ok := send.common["session_id"].(string)
	if !ok || sessionID == "" {
		t.Fatalf("common session_id = %v, want non-empty string", send.common["session_id"])
	}
	if sessionID == "spoofed" {
		t.Fatal("common session_id used renderer-supplied spoofed value")
	}
	if send.common["app_version"] != "0.0.0" {
		t.Fatalf("common app_version = %v, want 0.0.0", send.common["app_version"])
	}
	osName, ok := send.common["os"].(string)
	if !ok || osName == "" {
		t.Fatalf("common os = %v, want non-empty string", send.common["os"])
	}

	if len(send.events) != 1 {
		t.Fatalf("sent events = %d, want 1", len(send.events))
	}
	event := send.events[0]
	if event.Name != "workspace.opened" {
		t.Fatalf("event name = %q, want workspace.opened", event.Name)
	}
	if event.ClientTS != 1749124800000 {
		t.Fatalf("event client ts = %d, want 1749124800000", event.ClientTS)
	}
	if event.Params["source"] != "dashboard" {
		t.Fatalf("event source param = %v, want dashboard", event.Params["source"])
	}
	for _, key := range []string{"device_id", "session_id", "app_version", "os"} {
		if _, ok := event.Params[key]; ok {
			t.Fatalf("event params contains daemon-owned key %q", key)
		}
	}

	if len(debugPublisher.events) != 1 {
		t.Fatalf("debug events = %d, want 1", len(debugPublisher.events))
	}
	debugEvent := debugPublisher.events[0]
	if debugEvent.Name != "workspace.opened" {
		t.Fatalf("debug event name = %q, want workspace.opened", debugEvent.Name)
	}
	if debugEvent.ClientTS != 1749124800000 {
		t.Fatalf("debug event client ts = %d, want 1749124800000", debugEvent.ClientTS)
	}
	if debugEvent.Params["source"] != "dashboard" {
		t.Fatalf("debug source param = %v, want dashboard", debugEvent.Params["source"])
	}
	if debugEvent.Params["device_id"] != send.common["device_id"] {
		t.Fatalf("debug device_id = %v, want final common %v", debugEvent.Params["device_id"], send.common["device_id"])
	}
	if debugEvent.Params["session_id"] != send.common["session_id"] {
		t.Fatalf("debug session_id = %v, want final common %v", debugEvent.Params["session_id"], send.common["session_id"])
	}
	if debugEvent.Params["app_version"] != "0.0.0" {
		t.Fatalf("debug app_version = %v, want 0.0.0", debugEvent.Params["app_version"])
	}
	if debugEvent.Params["os"] != send.common["os"] {
		t.Fatalf("debug os = %v, want final common %v", debugEvent.Params["os"], send.common["os"])
	}
}

func TestTeaReporterSkipsEmptyNameEvents(t *testing.T) {
	sdk := &fakeTeaSDK{}
	reporter, err := newTeaReporterWithSDK(Config{
		Analytics: tuttitypes.AnalyticsConfig{
			AppID:         20004092,
			AppKey:        "app-key",
			ChannelDomain: "https://example.test",
		},
		StateDir: t.TempDir(),
	}, sdk)
	if err != nil {
		t.Fatalf("newTeaReporterWithSDK() error = %v", err)
	}

	reporter.Track(context.Background(),
		Event{Name: "", ClientTS: 1, Params: map[string]any{"source": "blank"}},
		Event{Name: "workspace.opened", ClientTS: 2, Params: map[string]any{"source": "dashboard"}},
	)

	if len(sdk.sends) != 1 {
		t.Fatalf("Send calls = %d, want 1", len(sdk.sends))
	}
	if len(sdk.sends[0].events) != 1 {
		t.Fatalf("sent events = %d, want 1", len(sdk.sends[0].events))
	}
	if sdk.sends[0].events[0].Name != "workspace.opened" {
		t.Fatalf("sent event name = %q, want workspace.opened", sdk.sends[0].events[0].Name)
	}
}

func TestTeaReporterDefaultsZeroClientTSToCurrentTime(t *testing.T) {
	sdk := &fakeTeaSDK{}
	reporter, err := newTeaReporterWithSDK(Config{
		Analytics: tuttitypes.AnalyticsConfig{
			AppID:         20004092,
			AppKey:        "app-key",
			ChannelDomain: "https://example.test",
		},
		StateDir: t.TempDir(),
	}, sdk)
	if err != nil {
		t.Fatalf("newTeaReporterWithSDK() error = %v", err)
	}

	before := time.Now().UnixMilli()
	reporter.Track(context.Background(), Event{Name: "workspace.opened"})
	after := time.Now().UnixMilli()

	if len(sdk.sends) != 1 {
		t.Fatalf("Send calls = %d, want 1", len(sdk.sends))
	}
	if len(sdk.sends[0].events) != 1 {
		t.Fatalf("sent events = %d, want 1", len(sdk.sends[0].events))
	}
	got := sdk.sends[0].events[0].ClientTS
	if got < before || got > after {
		t.Fatalf("event client ts = %d, want between %d and %d", got, before, after)
	}
}

func TestTeaSDKSysConfBoundsLogsErrorsAndQueueWait(t *testing.T) {
	stateDir := t.TempDir()
	logDir := filepath.Join(stateDir, "analytics", "sdk-logs")

	conf := newTeaSDKSysConf(teaSDKConfig{
		AppID:         20004092,
		AppKey:        "app-key",
		ChannelDomain: "https://example.test",
		StateDir:      stateDir,
	}, logDir)

	if conf.SdkConfig.Mode != sdk.MODE_HTTP {
		t.Fatalf("SDK mode = %q, want %q", conf.SdkConfig.Mode, sdk.MODE_HTTP)
	}
	if conf.SdkConfig.Env != sdk.ENV_SAAS_NATIVE {
		t.Fatalf("SDK env = %q, want %q", conf.SdkConfig.Env, sdk.ENV_SAAS_NATIVE)
	}
	if conf.SdkConfig.LogLevel != "ERROR" {
		t.Fatalf("SDK log level = %q, want ERROR", conf.SdkConfig.LogLevel)
	}
	if conf.HttpConfig.HttpAddr != "https://example.test" {
		t.Fatalf("HTTP addr = %q, want https://example.test", conf.HttpConfig.HttpAddr)
	}
	if conf.AppKeys[20004092] != "app-key" {
		t.Fatalf("app key = %q, want app-key", conf.AppKeys[20004092])
	}
	if conf.BatchConfig.Enable {
		t.Fatal("batch config enabled, want disabled")
	}
	if conf.FileConfig.Path != filepath.Join(logDir, "datarangers.log") {
		t.Fatalf("file log path = %q, want controlled log dir", conf.FileConfig.Path)
	}
	if conf.FileConfig.ErrPath != filepath.Join(logDir, "error-datarangers.log") {
		t.Fatalf("error log path = %q, want controlled log dir", conf.FileConfig.ErrPath)
	}
	if conf.FileConfig.MaxSize < 1 || conf.FileConfig.MaxBackup < 0 || conf.FileConfig.MaxAge < 0 {
		t.Fatalf("invalid rotation bounds: %+v", conf.FileConfig)
	}
	if conf.ErrHandler == nil {
		t.Fatal("ErrHandler is nil")
	}
	if err := conf.ErrHandler([]interface{}{map[string]any{"device_id": "sensitive"}}, errors.New("send failed")); err != nil {
		t.Fatalf("ErrHandler error = %v, want nil", err)
	}
	if conf.AlwaysWriteToErrFile {
		t.Fatal("AlwaysWriteToErrFile = true, want false")
	}
	if conf.AsynConfig.Routine != 1 {
		t.Fatalf("async routine = %d, want 1", conf.AsynConfig.Routine)
	}
	if conf.AsynConfig.WaitTimeout <= 0 {
		t.Fatalf("async wait timeout = %d, want bounded positive value", conf.AsynConfig.WaitTimeout)
	}
}

func TestEnsureTeaSDKLogDirCreatesControlledLogDir(t *testing.T) {
	stateDir := t.TempDir()
	logDir, err := ensureTeaSDKLogDir(stateDir)
	if err != nil {
		t.Fatalf("ensureTeaSDKLogDir() error = %v", err)
	}
	if logDir != filepath.Join(stateDir, "analytics", "sdk-logs") {
		t.Fatalf("log dir = %q, want controlled analytics sdk log dir", logDir)
	}

	info, err := os.Stat(logDir)
	if err != nil {
		t.Fatalf("stat analytics sdk log dir error = %v", err)
	}
	if !info.IsDir() {
		t.Fatal("analytics sdk log path is not a directory")
	}
}

func TestTeaReporterCloseDelegatesToAdapter(t *testing.T) {
	sdk := &fakeTeaSDK{}
	reporter, err := newTeaReporterWithSDK(Config{
		Analytics: tuttitypes.AnalyticsConfig{
			AppID:         20004092,
			AppKey:        "app-key",
			ChannelDomain: "https://example.test",
		},
		StateDir: t.TempDir(),
	}, sdk)
	if err != nil {
		t.Fatalf("newTeaReporterWithSDK() error = %v", err)
	}

	if err := reporter.Close(); err != nil {
		t.Fatalf("Close() error = %v", err)
	}
	if !sdk.closed {
		t.Fatal("Close did not delegate to adapter")
	}
}
