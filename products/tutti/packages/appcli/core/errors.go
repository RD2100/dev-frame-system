package core

import (
	"errors"
	"strings"
)

var (
	ErrInvalidInput       = errors.New("invalid app cli input")
	ErrServiceUnavailable = errors.New("app cli service unavailable")
	ErrHandlerBadResponse = errors.New("app cli handler bad response")
	ErrHandlerFailed      = errors.New("app cli handler failed")
)

type InvokeError struct {
	Kind   error
	Reason string
	Err    error
}

func (e *InvokeError) Error() string {
	if e == nil {
		return ""
	}
	message := strings.TrimSpace(e.Reason)
	if e.Err != nil {
		if message != "" {
			message += ": "
		}
		message += e.Err.Error()
	}
	if message == "" && e.Kind != nil {
		message = e.Kind.Error()
	}
	return message
}

func (e *InvokeError) Unwrap() error {
	if e == nil {
		return nil
	}
	if e.Kind == nil {
		return e.Err
	}
	if e.Err == nil {
		return e.Kind
	}
	return errors.Join(e.Kind, e.Err)
}

func invokeError(kind error, reason string, err error) error {
	return &InvokeError{Kind: kind, Reason: strings.TrimSpace(reason), Err: err}
}

func InvokeErrorReason(err error) string {
	var invokeErr *InvokeError
	if errors.As(err, &invokeErr) {
		return invokeErr.Reason
	}
	return ""
}
