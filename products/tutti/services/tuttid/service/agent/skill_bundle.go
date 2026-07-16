package agent

import (
	"context"
	"strings"

	agentsidecarservice "github.com/tutti-os/tutti/services/tuttid/service/agentsidecar"
)

type SkillBundleInput struct {
	AgentSessionID string
	Provider       string
	BrowserUse     bool
	ComputerUse    bool
}

type SkillBundle = agentsidecarservice.SkillBundle
type SkillMaterializationFile = agentsidecarservice.SkillMaterializationFile
type SkillMaterializationRecord = agentsidecarservice.SkillMaterializationRecord
type RecommendedSystemPrompt = agentsidecarservice.RecommendedSystemPrompt

func (s *Service) GetSkillBundle(ctx context.Context, workspaceID string, input SkillBundleInput) (SkillBundle, error) {
	workspaceID = strings.TrimSpace(workspaceID)
	provider := strings.TrimSpace(input.Provider)
	if workspaceID == "" || provider == "" {
		return SkillBundle{}, ErrInvalidArgument
	}
	renderer, ok := s.RuntimePreparer.(agentsidecarservice.SkillBundleRenderer)
	if s.RuntimePreparer == nil || !ok {
		return SkillBundle{}, ErrSkillBundleUnavailable
	}
	return renderer.RenderSkillBundle(ctx, agentsidecarservice.PrepareInput{
		WorkspaceID:    workspaceID,
		AgentSessionID: strings.TrimSpace(input.AgentSessionID),
		Provider:       provider,
		BrowserUse:     input.BrowserUse,
		ComputerUse:    input.ComputerUse,
	})
}
