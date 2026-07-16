import type { DesktopRuntimeApi } from "@preload/types";
import type { DesktopAgentComposerDefaultsPatch } from "@shared/preferences";
import type { DesktopAgentGUIProvider } from "../desktopAgentGUINodeState";
import { normalizedDesktopAgentComposerDefaultValue } from "../services/internal/desktopAgentComposerDefaultsWriteGate.ts";

export function logAgentComposerDefaultsDiagnostic(input: {
  defaults: DesktopAgentComposerDefaultsPatch;
  error?: unknown;
  event:
    | "agent.gui.composer_defaults.remembered"
    | "agent.gui.composer_defaults.remember_failed";
  provider: DesktopAgentGUIProvider;
  runtimeApi?: Pick<DesktopRuntimeApi, "logTerminalDiagnostic">;
  workspaceId: string;
}): void {
  if (!input.runtimeApi) {
    return;
  }
  void input.runtimeApi.logTerminalDiagnostic({
    details: {
      defaultModel:
        normalizedDesktopAgentComposerDefaultValue(input.defaults.model) ||
        null,
      defaultPermissionModeId:
        normalizedDesktopAgentComposerDefaultValue(
          input.defaults.permissionModeId
        ) || null,
      defaultReasoningEffort:
        normalizedDesktopAgentComposerDefaultValue(
          input.defaults.reasoningEffort
        ) || null,
      ...(input.error ? { error: stringifyDiagnosticError(input.error) } : {}),
      provider: input.provider
    },
    event: input.event,
    level: input.error ? "warn" : "info",
    workspaceId: input.workspaceId
  });
}

export function logAgentGUIConversationRailPreferenceDiagnostic(input: {
  collapsed: boolean;
  error?: unknown;
  provider: DesktopAgentGUIProvider;
  runtimeApi?: Pick<DesktopRuntimeApi, "logTerminalDiagnostic">;
  workspaceId: string;
}): void {
  if (!input.runtimeApi) {
    return;
  }
  void input.runtimeApi.logTerminalDiagnostic({
    details: {
      collapsed: input.collapsed,
      ...(input.error ? { error: stringifyDiagnosticError(input.error) } : {}),
      provider: input.provider
    },
    event: input.error
      ? "agent.gui.conversation_rail_preference.remember_failed"
      : "agent.gui.conversation_rail_preference.remembered",
    level: input.error ? "warn" : "info",
    workspaceId: input.workspaceId
  });
}

export function stringifyDiagnosticError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
