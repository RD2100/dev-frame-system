package agent

import (
	"context"
	"strings"
)

func (s *Service) ListGitBranches(ctx context.Context, workspaceID string, agentSessionID string) (GitBranches, error) {
	workspaceID = strings.TrimSpace(workspaceID)
	agentSessionID = strings.TrimSpace(agentSessionID)
	if workspaceID == "" || agentSessionID == "" {
		return GitBranches{}, ErrInvalidArgument
	}
	session, err := s.get(ctx, workspaceID, agentSessionID, false)
	if err != nil {
		return GitBranches{}, err
	}
	return listGitBranches(ctx, session.Cwd)
}

// ListGitBranchesForPath lists local git branches for a workspace working
// directory before any agent session exists (e.g. the empty-hero composer's
// selected project path). It mirrors the graceful degradation of the
// session-scoped path: a non-git or missing directory yields an empty result.
func (*Service) ListGitBranchesForPath(ctx context.Context, workspaceID string, workingDirectory string) (GitBranches, error) {
	workspaceID = strings.TrimSpace(workspaceID)
	workingDirectory = strings.TrimSpace(workingDirectory)
	if workspaceID == "" || workingDirectory == "" {
		return GitBranches{}, ErrInvalidArgument
	}
	return listGitBranches(ctx, workingDirectory)
}
