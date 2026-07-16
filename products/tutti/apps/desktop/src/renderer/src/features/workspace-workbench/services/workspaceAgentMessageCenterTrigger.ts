export type WorkspaceAgentMessageCenterTriggerKind = "waiting" | "running";

export interface WorkspaceAgentMessageCenterTrigger {
  count: number;
  kind: WorkspaceAgentMessageCenterTriggerKind;
  translationKey:
    | "workspace.agentMessageCenter.waitingCount"
    | "workspace.agentMessageCenter.runningCount";
}

export function resolveWorkspaceAgentMessageCenterTrigger(input: {
  runningCount: number;
  waitingCount: number;
}): WorkspaceAgentMessageCenterTrigger {
  if (input.waitingCount > 0) {
    return {
      count: input.waitingCount,
      kind: "waiting",
      translationKey: "workspace.agentMessageCenter.waitingCount"
    };
  }
  if (input.runningCount > 0) {
    return {
      count: input.runningCount,
      kind: "running",
      translationKey: "workspace.agentMessageCenter.runningCount"
    };
  }
  return {
    count: 0,
    kind: "waiting",
    translationKey: "workspace.agentMessageCenter.waitingCount"
  };
}
