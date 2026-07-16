package events

import (
	"context"
	"time"

	reporterservice "github.com/tutti-os/tutti/services/tuttid/service/reporter"
)

func Track(ctx context.Context, reporter reporterservice.Reporter, name string, params map[string]any) {
	if reporter == nil {
		return
	}
	reporter.Track(ctx, reporterservice.Event{
		Name:     name,
		ClientTS: time.Now().UnixMilli(),
		Params:   params,
	})
}
