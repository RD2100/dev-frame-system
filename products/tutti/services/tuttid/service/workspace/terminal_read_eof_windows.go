//go:build windows

package workspace

import (
	"errors"
	"io"
)

func isTerminalReadEOF(err error) bool {
	return errors.Is(err, io.EOF)
}
