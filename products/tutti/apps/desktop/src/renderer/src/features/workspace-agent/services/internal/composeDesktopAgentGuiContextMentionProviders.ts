import { AGENT_CONTEXT_MENTION_PROVIDER_IDS } from "@tutti-os/agent-gui/context-mention-provider";
import type { AgentContextMentionProvider } from "@tutti-os/agent-gui/context-mention-provider";

/**
 * Single source of truth for how the desktop agent GUI assembles its effective
 * `@`-mention provider set from the base providers. Both the live composer
 * (`DesktopAgentGUIWorkbenchBody`) and the startup cache warm-up go through this
 * so the resulting provider id set — and therefore the browse cache key — stays
 * identical. Keep the id-set composition here; callers supply the already-built
 * desktop-specific providers (so React callers can memoize them) and an optional
 * dock-file wrapper (only available once a workbench host exists).
 */
export function composeDesktopAgentGuiContextMentionProviders(input: {
  baseProviders: readonly AgentContextMentionProvider[];
  agentGeneratedFileMentionProvider: AgentContextMentionProvider;
  workspaceAppMentionProvider: AgentContextMentionProvider | null;
  wrapBaseProvider?: (
    provider: AgentContextMentionProvider
  ) => AgentContextMentionProvider;
}): AgentContextMentionProvider[] {
  const wrapBaseProvider = input.wrapBaseProvider ?? ((provider) => provider);
  return [
    ...input.baseProviders
      .filter(
        (provider) =>
          provider.id !== AGENT_CONTEXT_MENTION_PROVIDER_IDS.workspaceApp
      )
      .map(wrapBaseProvider),
    input.agentGeneratedFileMentionProvider,
    ...(input.workspaceAppMentionProvider
      ? [input.workspaceAppMentionProvider]
      : [])
  ];
}
