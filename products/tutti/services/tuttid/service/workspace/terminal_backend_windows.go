//go:build windows

package workspace

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"sync"

	"github.com/UserExistsError/conpty"
)

type windowsTerminalBackend struct {
	cpty      *conpty.ConPty
	closeOnce sync.Once
	closeErr  error
	ctx       context.Context
	cancel    context.CancelFunc
}

func newTerminalBackend(shell string, _ []string, cwd string, env []string, cols int, rows int) (terminalBackend, error) {
	fullShell, err := exec.LookPath(shell)
	if err != nil {
		return nil, fmt.Errorf("resolve windows shell %q: %w", shell, err)
	}

	commandLine := fullShell
	if strings.ContainsAny(fullShell, " \t") {
		commandLine = `"` + fullShell + `"`
	}

	options := []conpty.ConPtyOption{
		conpty.ConPtyDimensions(cols, rows),
		conpty.ConPtyWorkDir(cwd),
		conpty.ConPtyEnv(env),
	}

	cpty, err := conpty.Start(commandLine, options...)
	if err != nil {
		if errors.Is(err, conpty.ErrConPtyUnsupported) {
			return nil, fmt.Errorf("ConPTY is not available on this system")
		}
		return nil, fmt.Errorf("start conpty: %w", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	return &windowsTerminalBackend{cpty: cpty, ctx: ctx, cancel: cancel}, nil
}

func (b *windowsTerminalBackend) Read(p []byte) (int, error)  { return b.cpty.Read(p) }
func (b *windowsTerminalBackend) Write(p []byte) (int, error) { return b.cpty.Write(p) }
func (b *windowsTerminalBackend) Pid() int                    { return b.cpty.Pid() }
func (b *windowsTerminalBackend) Fd() uintptr                 { return 0 }

func (b *windowsTerminalBackend) Resize(cols int, rows int) error {
	return b.cpty.Resize(cols, rows)
}

func (b *windowsTerminalBackend) Wait() terminalWaitResult {
	code, err := b.cpty.Wait(b.ctx)
	if err != nil {
		return terminalWaitResult{Err: err}
	}
	c := int(code)
	return terminalWaitResult{ExitCode: &c}
}

func (b *windowsTerminalBackend) Kill() error {
	return b.doClose()
}

func (b *windowsTerminalBackend) Close() error {
	return b.doClose()
}

func (b *windowsTerminalBackend) doClose() error {
	b.closeOnce.Do(func() {
		b.cancel()
		b.closeErr = b.cpty.Close()
	})
	return b.closeErr
}
