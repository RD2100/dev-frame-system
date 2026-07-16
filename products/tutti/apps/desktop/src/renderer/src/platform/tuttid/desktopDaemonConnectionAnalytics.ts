import type {
  TuttidEventStreamClient,
  TuttidEventStreamConnectionState
} from "@tutti-os/client-tuttid-ts";
import type { IReporterService } from "../../features/analytics/services/reporterService.interface.ts";

export interface DesktopDaemonConnectionAnalyticsLease {
  release(): void;
}

export function startDesktopDaemonConnectionAnalytics(input: {
  eventStreamClient: Pick<TuttidEventStreamClient, "subscribeConnectionState">;
  now?: () => number;
  reporterService: Pick<IReporterService, "trackEvents">;
}): DesktopDaemonConnectionAnalyticsLease {
  const now = input.now ?? Date.now;
  let hasConnected = false;
  let disconnectedAt: number | null = null;

  const unsubscribe = input.eventStreamClient.subscribeConnectionState(
    (state) => {
      if (state === "connected") {
        if (disconnectedAt !== null) {
          const reconnectedAt = now();
          void reportDaemonDisconnectionCycle({
            disconnectedAt,
            downtimeMs: Math.max(0, reconnectedAt - disconnectedAt),
            reconnectedAt,
            reporterService: input.reporterService
          });
          disconnectedAt = null;
        }
        hasConnected = true;
        return;
      }

      if (state === "disconnected" && hasConnected && disconnectedAt === null) {
        disconnectedAt = now();
      }
    }
  );

  return {
    release() {
      unsubscribe();
    }
  };
}

async function reportDaemonDisconnectionCycle(input: {
  disconnectedAt: number;
  downtimeMs: number;
  reconnectedAt: number;
  reporterService: Pick<IReporterService, "trackEvents">;
}): Promise<void> {
  await input.reporterService.trackEvents([
    {
      clientTS: input.disconnectedAt,
      name: "daemon.disconnected",
      params: {
        reason: "unknown"
      }
    },
    {
      clientTS: input.reconnectedAt,
      name: "daemon.reconnected",
      params: {
        downtime_ms: input.downtimeMs
      }
    }
  ]);
}

export type { TuttidEventStreamConnectionState };
