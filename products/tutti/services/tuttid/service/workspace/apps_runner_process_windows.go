//go:build windows

package workspace

import (
	"context"
	"os/exec"
	"strconv"
	"time"

	tuttitypes "github.com/tutti-os/tutti/services/tuttid/types"
)

const windowsTreeKillTimeout = 500 * time.Millisecond

func prepareAppProcessCommand(*exec.Cmd) {}

func interruptAppProcess(command *exec.Cmd) error {
	return killAppProcess(command)
}

func killAppProcess(command *exec.Cmd) error {
	if command == nil || command.Process == nil {
		return nil
	}
	pid := command.Process.Pid
	ctx, cancel := context.WithTimeout(context.Background(), windowsTreeKillTimeout)
	defer cancel()

	taskkill := exec.CommandContext(ctx, "taskkill.exe", "/PID", strconv.Itoa(pid), "/T", "/F")
	if err := taskkill.Run(); err != nil {
		if !tuttitypes.ProcessExists(pid) {
			return nil
		}
		return command.Process.Kill()
	}
	return nil
}
