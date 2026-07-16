import type {
  TerminalDiagnostics,
  TerminalDiagnosticEvent
} from "@tutti-os/workspace-terminal/contracts";
import type { TerminalOpenedParams } from "../../../analytics/reporters/terminal-opened/types.ts";
import {
  createAnalyticsOpenedSourceParams,
  type AnalyticsOpenSource
} from "../../../analytics/reporters/openedSource.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";

export function createTerminalAnalyticsDiagnostics(input: {
  analytics: ReturnType<typeof createTerminalSurfaceAnalytics>;
  baseDiagnostics: TerminalDiagnostics;
}): TerminalDiagnostics {
  return {
    log(event, details) {
      input.baseDiagnostics.log(event, details);
      input.analytics.handleDiagnostic(event, details);
    }
  };
}

export function createTerminalSurfaceAnalytics(input: {
  reporterService?: Pick<IReporterService, "trackEvents">;
}) {
  const openedParamsByNodeId = new Map<string, TerminalOpenedParams>();
  const activeNodes = new Map<
    string,
    {
      closeTimer: ReturnType<typeof globalThis.setTimeout> | null;
      openedParams: TerminalOpenedParams;
      openedAt: number;
    }
  >();

  return {
    handleDiagnostic(
      event: TerminalDiagnosticEvent,
      details?: Record<string, string | number | boolean | null>
    ) {
      const reporterService = input.reporterService;
      const nodeId =
        typeof details?.nodeId === "string" ? details.nodeId : null;
      if (!reporterService || !nodeId) {
        return;
      }

      if (event === "mount") {
        const existing = activeNodes.get(nodeId);
        if (existing) {
          if (existing.closeTimer !== null) {
            globalThis.clearTimeout(existing.closeTimer);
            existing.closeTimer = null;
          }
          return;
        }

        const openedAt = Date.now();
        const openedParams =
          openedParamsByNodeId.get(nodeId) ??
          createAnalyticsOpenedSourceParams("restore");
        activeNodes.set(nodeId, {
          closeTimer: null,
          openedParams,
          openedAt
        });
        void reporterService.trackEvents([
          {
            clientTS: openedAt,
            name: "terminal.opened",
            params: openedParams
          }
        ]);
        return;
      }

      if (event !== "dispose") {
        return;
      }

      const active = activeNodes.get(nodeId);
      if (!active || active.closeTimer !== null) {
        return;
      }

      active.closeTimer = globalThis.setTimeout(() => {
        const current = activeNodes.get(nodeId);
        if (current !== active) {
          return;
        }

        activeNodes.delete(nodeId);
        openedParamsByNodeId.delete(nodeId);
        const closedAt = Date.now();
        void reporterService.trackEvents([
          {
            clientTS: closedAt,
            name: "terminal.closed",
            params: {
              duration_ms: Math.max(0, closedAt - active.openedAt)
            }
          }
        ]);
      }, 0);
    },
    observeNode(input: { nodeId: string; openedParams: TerminalOpenedParams }) {
      openedParamsByNodeId.set(input.nodeId, input.openedParams);
    }
  };
}

export function resolveTerminalOpenedParams(context: {
  node: { data: { activation?: { payload?: unknown } | null } };
}): TerminalOpenedParams {
  const payload = context.node.data.activation?.payload;
  if (payload && typeof payload === "object") {
    const typed = payload as { trigger?: unknown };
    if (isTerminalOpenedSource(typed.trigger)) {
      return createAnalyticsOpenedSourceParams(typed.trigger);
    }
  }

  return createAnalyticsOpenedSourceParams("restore");
}

function isTerminalOpenedSource(value: unknown): value is AnalyticsOpenSource {
  return (
    value === "agent_command" ||
    value === "dock" ||
    value === "keyboard" ||
    value === "launchpad" ||
    value === "restore"
  );
}
