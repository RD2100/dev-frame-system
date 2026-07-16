import {
  desktopIpcChannels,
  type DesktopTerminalStreamUrlRequest,
  type DesktopBackendConfig,
  type DesktopRendererDiagnosticPayload,
  type DesktopRuntimeLogLevel,
  type DesktopTerminalDiagnosticPayload
} from "../../shared/contracts/ipc";
import type { DesktopLogger } from "../logging";
import {
  resolveDesktopDaemonBaseUrl,
  resolveDesktopBusinessEventStreamUrl,
  resolveDesktopTerminalStreamUrl,
  type DesktopDaemonEndpoint
} from "../transport/paths";
import { listDesktopWorkspaceAgentProbes } from "../agentProviderUsageProbe";
import { registerDesktopIpcHandler } from "./handle";

export function registerRuntimeIpc(
  endpoint: DesktopDaemonEndpoint,
  logger: DesktopLogger
): void {
  registerDesktopIpcHandler(desktopIpcChannels.runtime.getBackendConfig, () =>
    resolveBackendConfig(endpoint)
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.runtime.getBusinessEventStreamUrl,
    () => resolveBusinessEventStreamUrl(endpoint)
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.runtime.listWorkspaceAgentProbes,
    (_event, input) => listDesktopWorkspaceAgentProbes(input)
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.runtime.getTerminalStreamUrl,
    (_event, input) => resolveTerminalStreamUrl(endpoint, input)
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.runtime.logTerminalDiagnostic,
    (_event, input) => {
      logTerminalDiagnostic(logger, input);
    }
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.runtime.logRendererDiagnostic,
    (_event, input) => {
      logRendererDiagnostic(logger, input);
    }
  );
}

function resolveBackendConfig(
  endpoint: DesktopDaemonEndpoint
): DesktopBackendConfig {
  return {
    accessToken: endpoint.accessToken,
    baseUrl: resolveDesktopDaemonBaseUrl(endpoint)
  };
}

function resolveTerminalStreamUrl(
  endpoint: DesktopDaemonEndpoint,
  input: DesktopTerminalStreamUrlRequest
): string {
  return resolveDesktopTerminalStreamUrl(endpoint, input);
}

function resolveBusinessEventStreamUrl(
  endpoint: DesktopDaemonEndpoint
): string {
  return resolveDesktopBusinessEventStreamUrl(endpoint);
}

function logTerminalDiagnostic(
  logger: DesktopLogger,
  input: DesktopTerminalDiagnosticPayload
): void {
  const log = resolveLogMethod(logger, input.level ?? "info");
  log("terminal diagnostic", {
    details: input.details ?? {},
    terminal_event: input.event,
    terminal_node_id: input.nodeId ?? null,
    terminal_session_id: input.sessionId ?? null,
    workspace_id: input.workspaceId ?? null
  });
}

function logRendererDiagnostic(
  logger: DesktopLogger,
  input: DesktopRendererDiagnosticPayload
): void {
  const log = resolveLogMethod(logger, input.level ?? "info");
  log("renderer diagnostic", {
    renderer_details: input.details ?? {},
    renderer_event: input.event,
    renderer_source: input.source,
    workspace_id: input.workspaceId ?? null
  });
}

function resolveLogMethod(
  logger: DesktopLogger,
  level: DesktopRuntimeLogLevel
): (message: string, fields?: Record<string, unknown>) => void {
  switch (level) {
    case "debug":
      return logger.debug.bind(logger);
    case "warn":
      return logger.warn.bind(logger);
    case "error":
      return logger.error.bind(logger);
    default:
      return logger.info.bind(logger);
  }
}
