package reporter

import (
	"context"
	"runtime"
	"time"

	"github.com/google/uuid"
)

type DebugReporter struct {
	deviceID   string
	sessionID  string
	appVersion string
	osName     string
	debug      DebugPublisher
}

func NewDebugReporter(config Config) (*DebugReporter, error) {
	deviceID, err := loadOrCreateDeviceID(config.StateDir)
	if err != nil {
		return nil, err
	}
	return &DebugReporter{
		deviceID:   deviceID,
		sessionID:  uuid.NewString(),
		appVersion: config.Analytics.AppVersion,
		osName:     runtime.GOOS,
		debug:      config.DebugPublisher,
	}, nil
}

func (r *DebugReporter) Track(ctx context.Context, events ...Event) {
	if r.debug == nil || len(events) == 0 {
		return
	}

	common := r.commonParams()
	debugEvents := make([]DebugEvent, 0, len(events))
	for _, event := range events {
		if event.Name == "" {
			continue
		}
		clientTS := event.ClientTS
		if clientTS == 0 {
			clientTS = time.Now().UnixMilli()
		}
		params := copyParams(event.Params)
		if params == nil {
			params = map[string]any{}
		}
		for _, key := range []string{"device_id", "session_id", "app_version", "os"} {
			delete(params, key)
		}
		for key, value := range common {
			params[key] = value
		}
		debugEvents = append(debugEvents, DebugEvent{
			Name:     event.Name,
			ClientTS: clientTS,
			Params:   params,
		})
	}
	if len(debugEvents) == 0 {
		return
	}

	r.debug.PublishAnalyticsDebugEvents(ctx, debugEvents)
}

func (*DebugReporter) Close() error {
	return nil
}

func (r *DebugReporter) commonParams() map[string]any {
	return map[string]any{
		"device_id":   r.deviceID,
		"session_id":  r.sessionID,
		"app_version": r.appVersion,
		"os":          r.osName,
	}
}
