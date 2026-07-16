import assert from "node:assert/strict";
import test from "node:test";
import {
  AGENT_CONTEXT_MENTION_PROVIDER_IDS,
  type AgentContextMentionProvider
} from "@tutti-os/agent-gui/context-mention-provider";
import { composeDesktopAgentGuiContextMentionProviders } from "./composeDesktopAgentGuiContextMentionProviders.ts";

test("desktop Agent GUI mention composition reuses the daemon-backed workspace app provider", () => {
  const fileProvider = createMentionProvider(
    AGENT_CONTEXT_MENTION_PROVIDER_IDS.file
  );
  const baseWorkspaceAppProvider = createMentionProvider(
    AGENT_CONTEXT_MENTION_PROVIDER_IDS.workspaceApp
  );
  const generatedFileProvider = createMentionProvider(
    AGENT_CONTEXT_MENTION_PROVIDER_IDS.agentGeneratedFile
  );

  const providers = composeDesktopAgentGuiContextMentionProviders({
    baseProviders: [fileProvider, baseWorkspaceAppProvider],
    agentGeneratedFileMentionProvider: generatedFileProvider,
    workspaceAppMentionProvider: baseWorkspaceAppProvider
  });

  assert.deepEqual(
    providers.map((provider) => provider.id),
    [
      AGENT_CONTEXT_MENTION_PROVIDER_IDS.file,
      AGENT_CONTEXT_MENTION_PROVIDER_IDS.agentGeneratedFile,
      AGENT_CONTEXT_MENTION_PROVIDER_IDS.workspaceApp
    ]
  );
  assert.equal(providers[2], baseWorkspaceAppProvider);
});

function createMentionProvider(id: string): AgentContextMentionProvider {
  return {
    id,
    trigger: "@",
    async query() {
      return [];
    },
    getItemKey: () => id,
    getItemLabel: () => id,
    toInsertResult: () => ({
      kind: "mention",
      mention: {
        entityId: id,
        label: id
      }
    })
  };
}
