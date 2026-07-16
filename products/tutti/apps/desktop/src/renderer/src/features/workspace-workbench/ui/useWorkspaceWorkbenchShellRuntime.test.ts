import assert from "node:assert/strict";
import test from "node:test";
import type { AgentGUIProviderTarget } from "@tutti-os/agent-gui";
import { filterWorkspaceAgentGuiProviderTargets } from "./workspaceAgentGuiProviderTargetFilter.ts";

const targets = [
  createTarget("codex"),
  createTarget("tutti-agent"),
  createTarget("claude-code")
];

test("filterWorkspaceAgentGuiProviderTargets disables Tutti Agent new-entry targets when the switch is off", () => {
  const filtered = filterWorkspaceAgentGuiProviderTargets(targets, {
    tuttiAgentSwitchEnabled: false
  });

  assert.deepEqual(
    filtered.map((target) => target.provider),
    ["codex", "tutti-agent", "claude-code"]
  );
  assert.equal(
    filtered.find((target) => target.provider === "tutti-agent")?.disabled,
    true
  );
});

test("filterWorkspaceAgentGuiProviderTargets keeps Tutti Agent new-entry targets when the switch is on", () => {
  const filtered = filterWorkspaceAgentGuiProviderTargets(targets, {
    tuttiAgentSwitchEnabled: true
  });

  assert.deepEqual(
    filtered.map((target) => target.provider),
    ["codex", "tutti-agent", "claude-code"]
  );
  assert.equal(
    filtered.find((target) => target.provider === "tutti-agent")?.disabled,
    undefined
  );
});

function createTarget(
  provider: AgentGUIProviderTarget["provider"]
): AgentGUIProviderTarget {
  return {
    targetId: `local:${provider}`,
    agentTargetId: `local:${provider}`,
    provider,
    label: provider,
    ref: {
      kind: "local",
      provider
    }
  };
}
