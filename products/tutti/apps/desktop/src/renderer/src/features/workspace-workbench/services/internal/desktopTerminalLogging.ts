import type {
  TerminalDiagnosticEvent,
  TerminalDiagnostics
} from "@tutti-os/workspace-terminal/contracts";
import type { DesktopRuntimeApi } from "@preload/types";
import type {
  DesktopRuntimeLogLevel,
  DesktopTerminalDiagnosticDetails
} from "@shared/contracts/ipc";

export function createDesktopTerminalDiagnostics(input: {
  runtimeApi: DesktopRuntimeApi;
  workspaceId: string;
}): TerminalDiagnostics {
  return {
    log(event, details) {
      logDesktopTerminalEvent({
        details,
        event: `surface.${event}`,
        level: resolveSurfaceDiagnosticLevel(event),
        nodeId: typeof details?.nodeId === "string" ? details.nodeId : null,
        runtimeApi: input.runtimeApi,
        sessionId:
          typeof details?.sessionId === "string" ? details.sessionId : null,
        workspaceId: input.workspaceId
      });
    }
  };
}

export function logDesktopTerminalEvent(input: {
  details?: DesktopTerminalDiagnosticDetails;
  event: string;
  level?: DesktopRuntimeLogLevel;
  nodeId?: string | null;
  runtimeApi: DesktopRuntimeApi;
  sessionId?: string | null;
  workspaceId: string;
}): void {
  void input.runtimeApi
    .logTerminalDiagnostic({
      details: input.details,
      event: input.event,
      level: input.level,
      nodeId: input.nodeId ?? null,
      sessionId: input.sessionId ?? null,
      workspaceId: input.workspaceId
    })
    .catch(() => undefined);
}

function resolveSurfaceDiagnosticLevel(
  event: TerminalDiagnosticEvent
): DesktopRuntimeLogLevel {
  switch (event) {
    case "hydration-gap":
      return "warn";
    case "attach-error":
    case "write-error":
      return "error";
    default:
      return "info";
  }
}
