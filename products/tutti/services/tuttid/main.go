package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	tuttiapp "github.com/tutti-os/tutti/services/tuttid/app"
	agentstatusservice "github.com/tutti-os/tutti/services/tuttid/service/agentstatus"
	tuttitypes "github.com/tutti-os/tutti/services/tuttid/types"
)

func main() {
	signal.Ignore(syscall.SIGPIPE)

	loggerSetup, err := tuttiapp.SetupLoggerFromEnv()
	if err != nil {
		fmt.Fprintf(os.Stderr, "configure tuttid logger: %v\n", err)
		os.Exit(1)
	}
	defer func() {
		if closeErr := loggerSetup.Close(); closeErr != nil {
			fmt.Fprintf(os.Stderr, "close tuttid logger: %v\n", closeErr)
		}
	}()

	slog.SetDefault(loggerSetup.Logger)
	recoverInstallCommandLock(slog.Default())

	if err := writePIDFile(); err != nil {
		fmt.Fprintf(os.Stderr, "write tuttid pid file: %v\n", err)
		os.Exit(1)
	}
	defer removePIDFile()

	parentCtx, cancelParentMonitor := contextWithDesktopParentMonitor(context.Background(), slog.Default())
	defer cancelParentMonitor()

	ctx, stop := signal.NotifyContext(parentCtx, syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	srv, listener, wiring, err := buildTuttiServer()
	if err != nil {
		fmt.Fprintf(os.Stderr, "build tuttid server: %v\n", err)
		os.Exit(1)
	}
	defer func() {
		_ = wiring.Close()
	}()

	if err := tuttiapp.New(srv, listener, loggerSetup.LogFilePath).Run(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "tuttid exited: %v\n", err)
		os.Exit(1)
	}
}

func writePIDFile() error {
	pidPath := tuttitypes.TuttidPIDPath()
	if err := os.MkdirAll(filepath.Dir(pidPath), 0o755); err != nil {
		return fmt.Errorf("create pid file directory: %w", err)
	}
	if err := os.WriteFile(pidPath, []byte(fmt.Sprintf("%d\n", os.Getpid())), 0o644); err != nil {
		return fmt.Errorf("write pid file: %w", err)
	}
	return nil
}

func removePIDFile() {
	_ = os.Remove(tuttitypes.TuttidPIDPath())
}

func recoverInstallCommandLock(logger *slog.Logger) {
	result, err := agentstatusservice.RecoverDefaultInstallCommandLock()
	if err != nil {
		logger.Warn("failed to recover npm install lock",
			"event", "tutti.agentstatus.install_lock.recovery_failed",
			"lock_path", result.LockPath,
			"error", err)
		return
	}
	if !result.Removed {
		return
	}
	logger.Info("recovered stale npm install lock",
		"event", "tutti.agentstatus.install_lock.recovered",
		"lock_path", result.LockPath,
		"pid", result.PID,
		"reason", result.Reason)
}

func contextWithDesktopParentMonitor(parent context.Context, logger *slog.Logger) (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithCancel(parent)
	parentPIDText := strings.TrimSpace(os.Getenv("TUTTI_DESKTOP_PARENT_PID"))
	if parentPIDText == "" {
		return ctx, cancel
	}

	parentPID, err := strconv.Atoi(parentPIDText)
	if err != nil || parentPID <= 1 {
		logger.Warn("invalid desktop parent pid; parent monitor disabled",
			"event", "tutti.parent_monitor.invalid_pid",
			"value", parentPIDText)
		return ctx, cancel
	}

	initialPPID := os.Getppid()
	logger.Info("tuttid desktop parent monitor started",
		"event", "tutti.parent_monitor.started",
		"parent_pid", parentPID,
		"initial_ppid", initialPPID)

	go func() {
		ticker := time.NewTicker(500 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				currentPPID := os.Getppid()
				parentWasDirect := initialPPID == parentPID
				parentChanged := parentWasDirect && currentPPID != parentPID
				parentGone := !tuttitypes.ProcessExists(parentPID)
				if !parentChanged && !parentGone {
					continue
				}
				logger.Warn("desktop parent process disappeared; shutting down tuttid",
					"event", "tutti.parent_monitor.parent_gone",
					"parent_pid", parentPID,
					"initial_ppid", initialPPID,
					"current_ppid", currentPPID,
					"parent_was_direct", parentWasDirect,
					"parent_changed", parentChanged,
					"parent_gone", parentGone)
				cancel()
				return
			}
		}
	}()

	return ctx, cancel
}
