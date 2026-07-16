import { afterEach, describe, expect, it } from "vitest";
import {
  closeAgentEnvPanel,
  getAgentEnvPanelStore,
  openAgentEnvPanel
} from "./agentEnvPanelStore";

afterEach(() => {
  closeAgentEnvPanel();
});

describe("agentEnvPanelStore", () => {
  it("opens with the requested provider + focus and bumps the sequence", () => {
    const before = getAgentEnvPanelStore().requestSequence;
    openAgentEnvPanel({ provider: "codex", focus: "upgrade" });
    const store = getAgentEnvPanelStore();
    expect(store.open).toBe(true);
    expect(store.provider).toBe("codex");
    expect(store.focus).toBe("upgrade");
    expect(store.requestSequence).toBe(before + 1);
  });

  it("re-bumps the sequence on a second open so the host re-detects", () => {
    openAgentEnvPanel({ provider: "codex", focus: "install" });
    const first = getAgentEnvPanelStore().requestSequence;
    openAgentEnvPanel({ provider: "codex", focus: "auth" });
    const store = getAgentEnvPanelStore();
    expect(store.requestSequence).toBe(first + 1);
    expect(store.focus).toBe("auth");
  });

  it("defaults provider/focus to null and closes", () => {
    openAgentEnvPanel();
    expect(getAgentEnvPanelStore().provider).toBeNull();
    expect(getAgentEnvPanelStore().focus).toBeNull();
    closeAgentEnvPanel();
    expect(getAgentEnvPanelStore().open).toBe(false);
  });
});
