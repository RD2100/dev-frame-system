import { describe, expect, it } from "vitest";
import { resolveSlashCommandsForProvider } from "./agentSlashCommandProviderPolicy";

describe("compact capability gating", () => {
  it("keeps compact when capability is unknown (legacy behavior)", () => {
    const commands = resolveSlashCommandsForProvider({
      provider: "codex",
      commands: [{ name: "compact" }, { name: "status" }]
    });
    expect(commands.some((command) => command.name === "compact")).toBe(true);
  });

  it("keeps compact when capability resolves true", () => {
    const commands = resolveSlashCommandsForProvider({
      provider: "codex",
      commands: [{ name: "compact" }],
      compactSupported: true
    });
    expect(commands.some((command) => command.name === "compact")).toBe(true);
  });

  it("drops compact (including fallback) when capability resolves false", () => {
    const commands = resolveSlashCommandsForProvider({
      provider: "codex",
      commands: [{ name: "compact" }, { name: "status" }],
      compactSupported: false
    });
    expect(commands.some((command) => command.name === "compact")).toBe(false);
    expect(commands.some((command) => command.name === "status")).toBe(true);
  });
});
