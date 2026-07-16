import type { AgentGUIProviderTarget } from "@tutti-os/agent-gui";

export function filterWorkspaceAgentGuiProviderTargets(
  targets: readonly AgentGUIProviderTarget[],
  input: { tuttiAgentSwitchEnabled: boolean }
): readonly AgentGUIProviderTarget[] {
  if (input.tuttiAgentSwitchEnabled) {
    return targets;
  }
  return targets.map((target) =>
    target.provider === "tutti-agent" ? { ...target, disabled: true } : target
  );
}
