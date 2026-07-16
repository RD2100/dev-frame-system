import type { WorkspaceAgentActivitySnapshot } from "../../../../../shared/workspaceAgentActivityTypes";

export function workspaceAgentSnapshotForConversations(
  snapshot: WorkspaceAgentActivitySnapshot
): WorkspaceAgentActivitySnapshot {
  return {
    ...snapshot,
    sessions: snapshot.sessions.filter((session) => session.visible !== false)
  } as WorkspaceAgentActivitySnapshot;
}
