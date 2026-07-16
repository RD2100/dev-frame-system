//go:build !windows

package workspace

import (
	"fmt"
	"os"
	"os/exec"

	"github.com/creack/pty"
)

type unixTerminalBackend struct {
	file *os.File
	cmd  *exec.Cmd
}

func newTerminalBackend(shell string, shellArgs []string, cwd string, env []string, cols int, rows int) (terminalBackend, error) {
	cmd := exec.Command(shell, shellArgs...)
	cmd.Dir = cwd
	cmd.Env = env

	file, err := pty.StartWithSize(cmd, &pty.Winsize{
		Cols: uint16(cols),
		Rows: uint16(rows),
	})
	if err != nil {
		return nil, fmt.Errorf("start terminal pty: %w", err)
	}

	return &unixTerminalBackend{file: file, cmd: cmd}, nil
}

func (b *unixTerminalBackend) Read(p []byte) (int, error)  { return b.file.Read(p) }
func (b *unixTerminalBackend) Write(p []byte) (int, error) { return b.file.Write(p) }
func (b *unixTerminalBackend) Close() error                { return b.file.Close() }
func (b *unixTerminalBackend) Pid() int                    { return b.cmd.Process.Pid }
func (b *unixTerminalBackend) Fd() uintptr                 { return b.file.Fd() }

func (b *unixTerminalBackend) Resize(cols int, rows int) error {
	return pty.Setsize(b.file, &pty.Winsize{Cols: uint16(cols), Rows: uint16(rows)})
}

func (b *unixTerminalBackend) Kill() error {
	if b.cmd.Process != nil {
		return b.cmd.Process.Kill()
	}
	return nil
}

func (b *unixTerminalBackend) Wait() terminalWaitResult {
	err := b.cmd.Wait()
	code, signal := describeTerminalExit(err)
	return terminalWaitResult{ExitCode: code, Signal: signal, Err: err}
}
