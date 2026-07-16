//go:build !windows

package workspace

import (
	"errors"
	"io"
	"syscall"
)

func isTerminalReadEOF(err error) bool {
	return errors.Is(err, io.EOF) || errors.Is(err, syscall.EIO)
}
