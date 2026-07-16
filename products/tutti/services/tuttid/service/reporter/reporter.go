package reporter

import (
	"context"

	tuttitypes "github.com/tutti-os/tutti/services/tuttid/types"
)

type Event struct {
	Name     string
	ClientTS int64
	Params   map[string]any
}

type DebugEvent struct {
	Name     string
	ClientTS int64
	Params   map[string]any
}

type DebugPublisher interface {
	PublishAnalyticsDebugEvents(context.Context, []DebugEvent)
}

type Reporter interface {
	Track(ctx context.Context, events ...Event)
	Close() error
}

type Config struct {
	Analytics      tuttitypes.AnalyticsConfig
	DebugPublisher DebugPublisher
	StateDir       string
}

func New(config Config) (Reporter, error) {
	if config.Analytics.Disabled {
		return &NoopReporter{}, nil
	}
	if config.Analytics.Debug {
		return NewDebugReporter(config)
	}
	if shouldUseNoop(config.Analytics) {
		return &NoopReporter{}, nil
	}
	return NewTeaReporter(config)
}

func shouldUseNoop(config tuttitypes.AnalyticsConfig) bool {
	return config.AppID == 0 ||
		config.AppKey == "" ||
		config.ChannelDomain == ""
}
