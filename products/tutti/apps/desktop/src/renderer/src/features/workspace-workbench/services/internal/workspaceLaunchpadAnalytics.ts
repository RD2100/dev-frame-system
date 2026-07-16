import { LaunchpadClosedReporter } from "../../../analytics/reporters/launchpad-closed/launchpadClosedReporter.ts";
import { LaunchpadItemLaunchedReporter } from "../../../analytics/reporters/launchpad-item-launched/launchpadItemLaunchedReporter.ts";
import { LaunchpadOpenedReporter } from "../../../analytics/reporters/launchpad-opened/launchpadOpenedReporter.ts";
import { createAnalyticsOpenedSourceParams } from "../../../analytics/reporters/openedSource.ts";
import { LaunchpadPageChangedReporter } from "../../../analytics/reporters/launchpad-page-changed/launchpadPageChangedReporter.ts";
import { LaunchpadSearchedReporter } from "../../../analytics/reporters/launchpad-searched/launchpadSearchedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";

export type WorkspaceLaunchpadOpenTrigger = "dock" | "keyboard";
export type WorkspaceLaunchpadAnalyticsItemType =
  | "agent"
  | "app"
  | "app_center"
  | "browser"
  | "files"
  | "issue_manager"
  | "terminal";

export interface WorkspaceLaunchpadAnalyticsController {
  closed(): void;
  itemLaunched(input: {
    appId: string | null;
    fromSearch: boolean;
    isComingSoon: boolean;
    itemType: WorkspaceLaunchpadAnalyticsItemType;
    provider: string | null;
  }): void;
  opened(input: {
    totalItems: number;
    trigger: WorkspaceLaunchpadOpenTrigger;
  }): void;
  pageChanged(input: { pageIndex: number; totalPages: number }): void;
  searched(input: { queryLength: number; resultCount: number }): void;
}

export interface WorkspaceLaunchpadAnalyticsDependencies {
  reporterService?: Pick<IReporterService, "trackEvents">;
  reporterNow?: () => number;
}

export function createWorkspaceLaunchpadAnalyticsController(
  dependencies: WorkspaceLaunchpadAnalyticsDependencies = {}
): WorkspaceLaunchpadAnalyticsController {
  let openedAt: number | null = null;
  let itemLaunched = false;
  const now = () => dependencies.reporterNow?.() ?? Date.now();
  const reporterDependencies = () => {
    if (!dependencies.reporterService) {
      return null;
    }
    return {
      now: dependencies.reporterNow,
      reporterService: dependencies.reporterService
    };
  };

  return {
    closed() {
      const reporter = reporterDependencies();
      if (!reporter || openedAt === null) {
        return;
      }

      const durationMs = Math.max(0, now() - openedAt);
      void new LaunchpadClosedReporter(
        {
          durationMs,
          itemLaunched
        },
        reporter
      ).report();
      openedAt = null;
      itemLaunched = false;
    },
    itemLaunched(input) {
      const reporter = reporterDependencies();
      itemLaunched = true;
      if (!reporter) {
        return;
      }

      void new LaunchpadItemLaunchedReporter(
        {
          appId: input.appId,
          fromSearch: input.fromSearch,
          isComingSoon: input.isComingSoon,
          itemType: input.itemType,
          provider: input.provider
        },
        reporter
      ).report();
    },
    opened(input) {
      const reporter = reporterDependencies();
      openedAt = now();
      itemLaunched = false;
      if (!reporter) {
        return;
      }

      void new LaunchpadOpenedReporter(
        {
          ...createAnalyticsOpenedSourceParams(input.trigger),
          totalItems: input.totalItems
        },
        reporter
      ).report();
    },
    pageChanged(input) {
      const reporter = reporterDependencies();
      if (!reporter) {
        return;
      }

      void new LaunchpadPageChangedReporter(
        {
          pageIndex: input.pageIndex,
          totalPages: input.totalPages
        },
        reporter
      ).report();
    },
    searched(input) {
      const reporter = reporterDependencies();
      if (!reporter) {
        return;
      }

      void new LaunchpadSearchedReporter(
        {
          queryLength: input.queryLength,
          resultCount: input.resultCount
        },
        reporter
      ).report();
    }
  };
}
