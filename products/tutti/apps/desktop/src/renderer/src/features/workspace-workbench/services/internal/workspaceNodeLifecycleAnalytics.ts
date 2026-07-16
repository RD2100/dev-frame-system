import type {
  AnalyticsReporterDependencies,
  AnalyticsReporterParams
} from "../../../analytics/reporters/baseReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";

interface AnalyticsReporter {
  report(): Promise<void>;
}

interface AnalyticsReporterConstructor<
  TParams extends AnalyticsReporterParams
> {
  new (
    params: TParams,
    dependencies: AnalyticsReporterDependencies
  ): AnalyticsReporter;
}

export interface TrackedWorkbenchNodeLease {
  release(): void;
}

export function createTrackedWorkbenchNodeLease<
  TOpenedParams extends AnalyticsReporterParams,
  TClosedParams extends AnalyticsReporterParams
>(input: {
  closedParams?: (input: { durationMs: number }) => TClosedParams;
  closedReporter?: AnalyticsReporterConstructor<TClosedParams>;
  openedParams: TOpenedParams;
  openedReporter: AnalyticsReporterConstructor<TOpenedParams>;
  reporterService?: Pick<IReporterService, "trackEvents">;
  reporterNow?: () => number;
}): TrackedWorkbenchNodeLease | null {
  if (!input.reporterService) {
    return null;
  }

  const now = () => input.reporterNow?.() ?? Date.now();
  const openedAt = now();
  const reporterDependencies = {
    now: input.reporterNow,
    reporterService: input.reporterService
  };
  void new input.openedReporter(
    input.openedParams,
    reporterDependencies
  ).report();

  return {
    release() {
      if (!input.closedReporter || !input.closedParams) {
        return;
      }

      const durationMs = Math.max(0, now() - openedAt);
      void new input.closedReporter(
        input.closedParams({ durationMs }),
        reporterDependencies
      ).report();
    }
  };
}

export function composeWorkbenchNodeLeases(
  ...leases: Array<TrackedWorkbenchNodeLease | null | void>
): TrackedWorkbenchNodeLease | null {
  const activeLeases = leases.filter(
    (lease): lease is TrackedWorkbenchNodeLease => Boolean(lease)
  );
  if (activeLeases.length === 0) {
    return null;
  }

  return {
    release() {
      for (const lease of activeLeases) {
        lease.release();
      }
    }
  };
}
