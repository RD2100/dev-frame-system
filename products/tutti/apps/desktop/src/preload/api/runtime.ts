import { desktopIpcChannels } from "../../shared/contracts/ipc";
import type { DesktopRuntimeApi } from "../types";
import { invokeDesktopApi } from "./invoke";

export function createRuntimeDesktopApi(): DesktopRuntimeApi {
  return {
    getBackendConfig() {
      return invokeDesktopApi(desktopIpcChannels.runtime.getBackendConfig);
    },
    getBusinessEventStreamUrl() {
      return invokeDesktopApi(
        desktopIpcChannels.runtime.getBusinessEventStreamUrl
      );
    },
    listWorkspaceAgentProbes(input) {
      return invokeDesktopApi(
        desktopIpcChannels.runtime.listWorkspaceAgentProbes,
        input
      );
    },
    logRendererDiagnostic(input) {
      return invokeDesktopApi(
        desktopIpcChannels.runtime.logRendererDiagnostic,
        input
      );
    },
    logTerminalDiagnostic(input) {
      return invokeDesktopApi(
        desktopIpcChannels.runtime.logTerminalDiagnostic,
        input
      );
    },
    getTerminalStreamUrl(input) {
      return invokeDesktopApi(
        desktopIpcChannels.runtime.getTerminalStreamUrl,
        input
      );
    }
  };
}
