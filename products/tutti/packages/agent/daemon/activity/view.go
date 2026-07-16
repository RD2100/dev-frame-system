package agentsessionstore

type SnapshotListener interface {
	OnSnapshotChanged(roomID string, snapshot WorkspaceAgentSnapshot)
}

type View interface {
	OnSessionAdded(roomID string, session WorkspaceAgentSession)
	OnSessionUpdated(roomID string, session WorkspaceAgentSession)
	OnSessionRemoved(roomID string, agentSessionID string)
	OnMessageUpdated(roomID string, agentSessionID string, message WorkspaceAgentSessionMessage)
	OnPresenceChanged(roomID string, presences []WorkspaceAgentPresence)
}
