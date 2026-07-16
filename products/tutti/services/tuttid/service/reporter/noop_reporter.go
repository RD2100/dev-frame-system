package reporter

import "context"

type NoopReporter struct{}

func (NoopReporter) Track(context.Context, ...Event) {}

func (NoopReporter) Close() error {
	return nil
}
