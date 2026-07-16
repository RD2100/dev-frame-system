import type { IAgentProviderStatusService } from "../agentProviderStatusService.interface.ts";
import { desktopManagedAgentProviders } from "./desktopManagedAgentProviders.ts";

export interface DesktopAgentProviderVisibilityRefreshOptions {
  document?: Pick<
    Document,
    "addEventListener" | "removeEventListener" | "visibilityState"
  >;
  minIntervalMs?: number;
  window?: Pick<Window, "addEventListener" | "removeEventListener">;
}

export function bindDesktopManagedAgentProviderVisibilityRefresh(
  service: Pick<IAgentProviderStatusService, "refresh">,
  options: DesktopAgentProviderVisibilityRefreshOptions = {}
): () => void {
  const windowRef =
    options.window ?? (typeof window !== "undefined" ? window : null);
  const documentRef =
    options.document ?? (typeof document !== "undefined" ? document : null);
  if (!windowRef || !documentRef) {
    return () => {};
  }

  const minIntervalMs = options.minIntervalMs ?? 10_000;
  const providers = [...desktopManagedAgentProviders];
  let lastRefreshAt = 0;

  const refreshStatuses = (): void => {
    if (documentRef.visibilityState !== "visible") {
      return;
    }
    const now = Date.now();
    if (now - lastRefreshAt < minIntervalMs) {
      return;
    }
    lastRefreshAt = now;
    void service.refresh(providers).catch(() => {});
  };

  windowRef.addEventListener("focus", refreshStatuses);
  documentRef.addEventListener("visibilitychange", refreshStatuses);
  return () => {
    windowRef.removeEventListener("focus", refreshStatuses);
    documentRef.removeEventListener("visibilitychange", refreshStatuses);
  };
}
