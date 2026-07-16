export interface WorkspaceAgentDecisionToastVisibilityInput {
  /** Whether the session's own AgentGUI conversation window is already open (not minimized). */
  agentGuiSessionOpen: boolean;
  /** Whether the message center panel is already open (item is already visible there). */
  messageCenterOpen: boolean;
  /** Whether the workspace window currently has OS focus and is visible. */
  windowForeground: boolean;
}

/**
 * The decision toast interrupts the user, so it should only pop up when the
 * workspace window is actually open and focused. When the window is in the
 * background the OS notification already covers the "please come back"
 * signal (see compositeNotificationService's background-only presentation),
 * and the pending decision remains available in the message center — the
 * toast itself would just be an unseen, disruptive interruption. Likewise,
 * when the session's own AgentGUI conversation window is already open, the
 * prompt is already visible inline there, so the toast would just duplicate it.
 */
export function shouldShowWorkspaceAgentDecisionToast(
  input: WorkspaceAgentDecisionToastVisibilityInput
): boolean {
  return (
    !input.messageCenterOpen &&
    input.windowForeground &&
    !input.agentGuiSessionOpen
  );
}
