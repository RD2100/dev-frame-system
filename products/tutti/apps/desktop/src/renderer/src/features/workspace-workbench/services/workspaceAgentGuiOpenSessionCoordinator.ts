const openSessionRefCountsByWorkspaceId = new Map<
  string,
  Map<string, number>
>();

/**
 * Lets a mounted, non-minimized AgentGUI node register the agent session it is
 * currently showing, so other parts of the workbench (e.g. the waiting-decision
 * toast) can tell whether that session's conversation is already visible to the
 * user and skip a redundant interruption. Mirrors the message center open
 * coordinator pattern.
 */
export function registerWorkspaceAgentGuiOpenSession(
  workspaceId: string,
  agentSessionId: string
): () => void {
  const normalizedWorkspaceId = workspaceId.trim();
  const normalizedAgentSessionId = agentSessionId.trim();
  if (!normalizedWorkspaceId || !normalizedAgentSessionId) {
    return () => {};
  }

  let refCounts = openSessionRefCountsByWorkspaceId.get(normalizedWorkspaceId);
  if (!refCounts) {
    refCounts = new Map<string, number>();
    openSessionRefCountsByWorkspaceId.set(normalizedWorkspaceId, refCounts);
  }
  refCounts.set(
    normalizedAgentSessionId,
    (refCounts.get(normalizedAgentSessionId) ?? 0) + 1
  );

  let released = false;
  return () => {
    if (released) {
      return;
    }
    released = true;
    const currentRefCounts = openSessionRefCountsByWorkspaceId.get(
      normalizedWorkspaceId
    );
    const nextCount =
      (currentRefCounts?.get(normalizedAgentSessionId) ?? 0) - 1;
    if (!currentRefCounts) {
      return;
    }
    if (nextCount <= 0) {
      currentRefCounts.delete(normalizedAgentSessionId);
      if (currentRefCounts.size === 0) {
        openSessionRefCountsByWorkspaceId.delete(normalizedWorkspaceId);
      }
    } else {
      currentRefCounts.set(normalizedAgentSessionId, nextCount);
    }
  };
}

export function isWorkspaceAgentGuiSessionOpen(
  workspaceId: string,
  agentSessionId: string
): boolean {
  const refCounts = openSessionRefCountsByWorkspaceId.get(workspaceId.trim());
  return (refCounts?.get(agentSessionId.trim()) ?? 0) > 0;
}
