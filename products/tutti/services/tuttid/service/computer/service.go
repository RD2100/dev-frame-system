package computer

import (
	"context"
	"strings"
	"sync"
	"time"

	agentruntime "github.com/tutti-os/tutti/packages/agent/daemon/runtime"
)

// defaultIdleTTL shuts a workspace's computer session (and cua-driver) down
// after a period with no tool calls.
const defaultIdleTTL = 5 * time.Minute

// Service drives the macOS desktop for agents via the `tutti computer` CLI.
// It owns one cua-driver subprocess per workspace, reused across CLI calls and
// torn down on idle or daemon shutdown.
type Service struct {
	transport agentruntime.ProcessTransport
	idleTTL   time.Duration

	mu       sync.Mutex
	sessions map[string]*computerSession
}

// NewService constructs a computer Service using a local process transport.
func NewService() *Service {
	return &Service{
		transport: agentruntime.NewLocalProcessTransport(),
		idleTTL:   defaultIdleTTL,
		sessions:  make(map[string]*computerSession),
	}
}

// CallTool invokes a cua-driver MCP tool against the workspace's computer
// session, lazily starting it on first use.
func (s *Service) CallTool(ctx context.Context, workspaceID, cwd, tool string, args map[string]any) (ToolResult, error) {
	workspaceID = strings.TrimSpace(workspaceID)

	if err := validateComputerReady(); err != nil {
		return ToolResult{}, err
	}

	session := s.getOrCreate(workspaceID)
	session.beginCall()
	defer session.endCall(func() { s.resetIdle(workspaceID, session) })

	if err := session.start(ctx, cwd); err != nil {
		// A failed start should not be cached; drop the session so the next
		// call retries (e.g. transient failure).
		s.Shutdown(workspaceID)
		return ToolResult{}, err
	}
	result, err := session.adaptToolCall(ctx, tool, args)
	if err != nil && session.client != nil && session.client.isClosed() {
		s.Shutdown(workspaceID)
	}
	return result, err
}

func (s *Service) getOrCreate(workspaceID string) *computerSession {
	s.mu.Lock()
	defer s.mu.Unlock()
	if session, ok := s.sessions[workspaceID]; ok {
		return session
	}
	session := &computerSession{
		transport: s.transport,
		command:   resolveComputerMCPCommand,
	}
	s.sessions[workspaceID] = session
	return session
}

func (s *Service) resetIdle(workspaceID string, session *computerSession) {
	if session.inFlightCount() != 0 {
		return
	}
	session.idleMu.Lock()
	defer session.idleMu.Unlock()
	if session.inFlightCount() != 0 {
		return
	}
	if session.idle != nil {
		session.idle.Stop()
	}
	session.idle = time.AfterFunc(s.idleTTL, func() { s.Shutdown(workspaceID) })
}

// Shutdown tears down a single workspace's computer session.
func (s *Service) Shutdown(workspaceID string) {
	s.mu.Lock()
	session := s.sessions[strings.TrimSpace(workspaceID)]
	delete(s.sessions, strings.TrimSpace(workspaceID))
	s.mu.Unlock()
	if session == nil {
		return
	}
	session.idleMu.Lock()
	if session.idle != nil {
		session.idle.Stop()
	}
	session.idleMu.Unlock()
	session.close()
}

// Close tears down all computer sessions (daemon shutdown).
func (s *Service) Close() {
	s.mu.Lock()
	sessions := s.sessions
	s.sessions = make(map[string]*computerSession)
	s.mu.Unlock()
	for _, session := range sessions {
		session.idleMu.Lock()
		if session.idle != nil {
			session.idle.Stop()
		}
		session.idleMu.Unlock()
		session.close()
	}
}
