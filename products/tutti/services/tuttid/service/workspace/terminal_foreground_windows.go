//go:build windows

package workspace

func (s *terminalRuntimeSession) foregroundProcess() (terminalForegroundProcess, bool) {
	return terminalForegroundProcess{}, false
}
