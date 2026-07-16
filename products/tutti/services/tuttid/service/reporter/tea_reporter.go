package reporter

import (
	"context"
	"runtime"
	"time"

	"github.com/google/uuid"
)

type TeaReporter struct {
	appID      int64
	deviceID   string
	sessionID  string
	appVersion string
	osName     string
	sdk        teaSDK
	debug      DebugPublisher
}

func NewTeaReporter(config Config) (*TeaReporter, error) {
	return newTeaReporterWithSDK(config, defaultTeaSDK{})
}

func newTeaReporterWithSDK(config Config, sdk teaSDK) (*TeaReporter, error) {
	deviceID, err := loadOrCreateDeviceID(config.StateDir)
	if err != nil {
		return nil, err
	}
	if err := sdk.Init(teaSDKConfig{
		AppID:         int64(config.Analytics.AppID),
		AppKey:        config.Analytics.AppKey,
		ChannelDomain: config.Analytics.ChannelDomain,
		StateDir:      config.StateDir,
	}); err != nil {
		return nil, err
	}
	return &TeaReporter{
		appID:      int64(config.Analytics.AppID),
		deviceID:   deviceID,
		sessionID:  uuid.NewString(),
		appVersion: config.Analytics.AppVersion,
		osName:     runtime.GOOS,
		sdk:        sdk,
		debug:      config.DebugPublisher,
	}, nil
}

func (r *TeaReporter) Track(ctx context.Context, events ...Event) {
	if len(events) == 0 {
		return
	}

	var sendEvents []teaSDKEvent
	for _, event := range events {
		if event.Name == "" {
			continue
		}
		clientTS := event.ClientTS
		if clientTS == 0 {
			clientTS = time.Now().UnixMilli()
		}
		params := copyParams(event.Params)
		for _, key := range []string{"device_id", "session_id", "app_version", "os"} {
			delete(params, key)
		}
		sendEvents = append(sendEvents, teaSDKEvent{
			Name:     event.Name,
			ClientTS: clientTS,
			Params:   params,
		})
	}
	if len(sendEvents) == 0 {
		return
	}

	common := r.commonParams()
	r.publishDebugEvents(ctx, sendEvents, common)
	_ = r.sdk.Send(r.appID, r.deviceID, sendEvents, common)
}

func (r *TeaReporter) Close() error {
	return r.sdk.Close()
}

func (r *TeaReporter) commonParams() map[string]any {
	return map[string]any{
		"device_id":   r.deviceID,
		"session_id":  r.sessionID,
		"app_version": r.appVersion,
		"os":          r.osName,
	}
}

func (r *TeaReporter) publishDebugEvents(ctx context.Context, events []teaSDKEvent, common map[string]any) {
	if r.debug == nil || len(events) == 0 {
		return
	}
	debugEvents := make([]DebugEvent, 0, len(events))
	for _, event := range events {
		params := copyParams(event.Params)
		if params == nil {
			params = map[string]any{}
		}
		for key, value := range common {
			params[key] = value
		}
		debugEvents = append(debugEvents, DebugEvent{
			Name:     event.Name,
			ClientTS: event.ClientTS,
			Params:   params,
		})
	}
	r.debug.PublishAnalyticsDebugEvents(ctx, debugEvents)
}

func copyParams(params map[string]any) map[string]any {
	if params == nil {
		return nil
	}
	copied := make(map[string]any, len(params))
	for key, value := range params {
		copied[key] = value
	}
	return copied
}
