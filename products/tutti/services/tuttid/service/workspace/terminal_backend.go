package workspace

import "io"

type terminalWaitResult struct {
	ExitCode *int
	Signal   *string
	Err      error
}

type terminalBackend interface {
	io.ReadWriteCloser
	Resize(cols int, rows int) error
	Wait() terminalWaitResult
	Pid() int
	Kill() error
	Fd() uintptr
}
