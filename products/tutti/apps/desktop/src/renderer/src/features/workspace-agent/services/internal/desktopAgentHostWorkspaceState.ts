import {
  agentSessionStateDefaultsFromSettings,
  type AgentHostAgentSessionComposerSettingsInput,
  type AgentHostAgentSessionStateDefaults
} from "./desktopAgentHostProjection.ts";

export interface DesktopAgentHostWorkspaceState {
  sessionStateDefaultsByAgentSessionId: Map<
    string,
    AgentHostAgentSessionStateDefaults
  >;
}

const agentHostWorkspaceStateByWorkspaceId = new Map<
  string,
  DesktopAgentHostWorkspaceState
>();

export function desktopAgentHostWorkspaceState(
  workspaceId: string
): DesktopAgentHostWorkspaceState {
  const normalizedWorkspaceId = workspaceId.trim() || "__default__";
  let state = agentHostWorkspaceStateByWorkspaceId.get(normalizedWorkspaceId);
  if (!state) {
    state = {
      sessionStateDefaultsByAgentSessionId: new Map<
        string,
        AgentHostAgentSessionStateDefaults
      >()
    };
    agentHostWorkspaceStateByWorkspaceId.set(normalizedWorkspaceId, state);
  }
  return state;
}

export function rememberAgentSessionStateDefaults(
  state: DesktopAgentHostWorkspaceState,
  tuttidSessionId: string,
  settings: AgentHostAgentSessionComposerSettingsInput | null | undefined
): void {
  const defaults = agentSessionStateDefaultsFromSettings(settings);
  if (!defaults) {
    return;
  }
  const normalizedTuttidSessionId = normalizeAgentSessionId(tuttidSessionId);
  if (normalizedTuttidSessionId) {
    state.sessionStateDefaultsByAgentSessionId.set(
      normalizedTuttidSessionId,
      defaults
    );
  }
}

export function resolveAgentSessionStateDefaults(
  state: DesktopAgentHostWorkspaceState,
  agentSessionId: string
): AgentHostAgentSessionStateDefaults | undefined {
  return state.sessionStateDefaultsByAgentSessionId.get(
    normalizeAgentSessionId(agentSessionId)
  );
}

function normalizeAgentSessionId(agentSessionId: string): string {
  return agentSessionId.trim();
}
