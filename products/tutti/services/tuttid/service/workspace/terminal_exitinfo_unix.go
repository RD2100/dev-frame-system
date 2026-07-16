//go:build !windows

package workspace

import (
	"errors"
	"os/exec"
	"syscall"
)

func describeTerminalExit(err error) (*int, *string) {
	var exitErr *exec.ExitError
	if !errors.As(err, &exitErr) {
		return nil, nil
	}

	if status, ok := exitErr.Sys().(syscall.WaitStatus); ok {
		if status.Signaled() {
			signal := status.Signal().String()
			return nil, &signal
		}
		if status.Exited() {
			code := status.ExitStatus()
			return &code, nil
		}
	}

	code := exitErr.ExitCode()
	if code < 0 {
		return nil, nil
	}
	return &code, nil
}
