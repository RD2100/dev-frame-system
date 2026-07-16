package agent

import (
	"context"
	"reflect"
	"strings"
	"time"
)

func serviceStreamEvents(ctx context.Context, events <-chan RuntimeStreamEvent) <-chan StreamEvent {
	out := make(chan StreamEvent)
	go func() {
		defer close(out)
		seq := int64(0)
		for event := range events {
			seq++
			select {
			case out <- StreamEvent{
				OccurredAt: occurredAtForStreamEvent(event),
				Payload: map[string]any{
					"data":      event.Data,
					"eventType": strings.TrimSpace(event.EventType),
				},
				Seq:  seq,
				Type: strings.TrimSpace(event.EventType),
			}:
			case <-ctx.Done():
				return
			}
		}
	}()
	return out
}

func occurredAtForStreamEvent(event RuntimeStreamEvent) time.Time {
	for _, fieldName := range []string{"OccurredAtUnixMS", "UpdatedAtUnixMS", "CreatedAtUnixMS"} {
		if timestamp := int64Field(event.Data, fieldName); timestamp > 0 {
			return time.Unix(0, timestamp*int64(time.Millisecond)).UTC()
		}
	}
	return time.Now().UTC()
}

func int64Field(value any, fieldName string) int64 {
	if value == nil {
		return 0
	}
	reflected := reflect.ValueOf(value)
	for reflected.Kind() == reflect.Pointer {
		if reflected.IsNil() {
			return 0
		}
		reflected = reflected.Elem()
	}
	if reflected.Kind() != reflect.Struct {
		return 0
	}
	field := reflected.FieldByName(fieldName)
	if !field.IsValid() {
		return 0
	}
	switch field.Kind() {
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return field.Int()
	default:
		return 0
	}
}
