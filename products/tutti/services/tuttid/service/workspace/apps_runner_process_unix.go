//go:build !windows

package workspace

import (
	"errors"
	"os/exec"
	"syscall"
)

func prepareAppProcessCommand(command *exec.Cmd) {
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
}

func interruptAppProcess(command *exec.Cmd) error {
	return signalAppProcessGroup(command, syscall.SIGINT)
}

func killAppProcess(command *exec.Cmd) error {
	return signalAppProcessGroup(command, syscall.SIGKILL)
}

func signalAppProcessGroup(command *exec.Cmd, signal syscall.Signal) error {
	if command == nil || command.Process == nil {
		return nil
	}
	if err := syscall.Kill(-command.Process.Pid, signal); err != nil {
		if errors.Is(err, syscall.ESRCH) {
			return nil
		}
		return command.Process.Signal(signal)
	}
	return nil
}
