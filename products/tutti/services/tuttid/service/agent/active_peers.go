package agent

import (
	"context"
	"strings"
)

type ActivePeer struct {
	Session      Session
	SelfRelation string
}

type ActivePeers struct {
	Agents         []ActivePeer
	SelfKnown      bool
	MayIncludeSelf bool
	Warning        string
}

func (s *Service) ListActivePeers(ctx context.Context, workspaceID string) (ActivePeers, error) {
	sessions, err := s.List(ctx, workspaceID)
	if err != nil {
		return ActivePeers{}, err
	}
	peers := make([]ActivePeer, 0)
	for _, session := range sessions {
		if !isActivePeerStatus(session.Status) {
			continue
		}
		peers = append(peers, ActivePeer{
			Session:      cloneSession(session),
			SelfRelation: "unknown",
		})
	}
	return ActivePeers{
		Agents:         peers,
		SelfKnown:      false,
		MayIncludeSelf: true,
		Warning:        "SELF_IDENTITY_UNAVAILABLE",
	}, nil
}

func isActivePeerStatus(status string) bool {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "working", "waiting", "running", "streaming", "active":
		return true
	default:
		return false
	}
}
