import { useSnapshot } from "valtio";
import { proxy } from "valtio/vanilla";

/**
 * Section the Agent Env panel (the片6 Setup Wizard / config panel) should scroll
 * to / emphasise when opened via a deep-link. The error card (片5) maps a domain
 * error code to one of these so the user lands on the relevant remediation.
 */
export type AgentEnvPanelFocus =
  | "detect"
  | "install"
  | "repair"
  | "upgrade"
  | "auth"
  | "network"
  | "registry";

export interface AgentEnvPanelRequest {
  open: boolean;
  provider: string | null;
  focus: AgentEnvPanelFocus | null;
  /**
   * Bumped on every openAgentEnvPanel() call. The host panel watches this to
   * re-run detection even when it is already open (e.g. a second deep-link).
   */
  requestSequence: number;
}

export interface OpenAgentEnvPanelInput {
  provider?: string | null;
  focus?: AgentEnvPanelFocus | null;
}

const agentEnvPanelStore = proxy<AgentEnvPanelRequest>({
  open: false,
  provider: null,
  focus: null,
  requestSequence: 0
});

/**
 * Open the agent environment panel. Safe to call from anywhere in the agent-gui
 * tree (rail footer entry, error-card deep-link). The host renders the actual
 * panel and reacts to this singleton store.
 */
export function openAgentEnvPanel(input?: OpenAgentEnvPanelInput): void {
  agentEnvPanelStore.open = true;
  agentEnvPanelStore.provider = input?.provider ?? null;
  agentEnvPanelStore.focus = input?.focus ?? null;
  agentEnvPanelStore.requestSequence += 1;
}

export function closeAgentEnvPanel(): void {
  agentEnvPanelStore.open = false;
}

/** Imperative read, mainly for tests. Components should use the hook. */
export function getAgentEnvPanelStore(): AgentEnvPanelRequest {
  return agentEnvPanelStore;
}

/** Reactive snapshot of the panel request for the host renderer. */
export function useAgentEnvPanelRequest(): AgentEnvPanelRequest {
  return useSnapshot(agentEnvPanelStore);
}
