---
"@tutti-os/agent-gui": minor
---

Add an `@tutti-os/agent-gui/agent-conversation` entry point exposing the standalone conversation-flow renderer (`AgentConversationFlow`, `AgentTranscriptView`, `AgentTranscriptSkeleton`) and the higher-level `WorkspaceAgentSessionDetail` wrapper (projects the conversation view model and defaults transcript labels from the package i18n), together with the view-model builders (`buildWorkspaceAgentSessionDetailViewModel`, `projectAgentConversationVM`, `reconcileProjectedAgentConversationVM`, `useProjectedAgentConversation`) and supporting types. This lets consumers render a single agent session's transcript outside the full AgentGUI node by building a session-detail view model from the session's timeline items.
