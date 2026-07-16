import type { DesktopRuntimeApi } from "@preload/types";
import { resolveDesktopEnvironment } from "@renderer/platform/desktop/resolveDesktopEnvironment";

export type RendererDiagnosticSink = (
  input: Parameters<DesktopRuntimeApi["logRendererDiagnostic"]>[0]
) => void;

export function createRendererDiagnosticSink(): RendererDiagnosticSink {
  const runtimeApi = resolveDesktopEnvironment(window.tutti).desktopApi.runtime;
  return (input) => {
    void runtimeApi.logRendererDiagnostic(input);
  };
}
