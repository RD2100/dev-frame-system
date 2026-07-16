import assert from "node:assert/strict";
import test from "node:test";
import type { ReporterEventInput } from "../../../analytics/services/reporterService.interface.ts";
import { createWorkspaceLaunchpadAnalyticsController } from "./workspaceLaunchpadAnalytics.ts";

test("workspace launchpad analytics tracks opened and closed duration", () => {
  const reporterCalls: ReporterEventInput[][] = [];
  let now = 1749124800000;
  const analytics = createWorkspaceLaunchpadAnalyticsController({
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => now
  });

  analytics.opened({
    totalItems: 12,
    trigger: "dock"
  });
  now = 1749124800320;
  analytics.closed();

  assert.deepEqual(reporterCalls, [
    [
      {
        clientTS: 1749124800000,
        name: "launchpad.opened",
        params: {
          source: "dock",
          total_items: 12,
          trigger: "manual"
        }
      }
    ],
    [
      {
        clientTS: 1749124800320,
        name: "launchpad.closed",
        params: {
          duration_ms: 320,
          item_launched: false
        }
      }
    ]
  ]);
});

test("workspace launchpad analytics marks closed events after item launch", () => {
  const reporterCalls: ReporterEventInput[][] = [];
  let now = 1749124800000;
  const analytics = createWorkspaceLaunchpadAnalyticsController({
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => now
  });

  analytics.opened({
    totalItems: 5,
    trigger: "keyboard"
  });
  analytics.itemLaunched({
    appId: "app-1",
    fromSearch: true,
    isComingSoon: false,
    itemType: "app",
    provider: null
  });
  now = 1749124800200;
  analytics.closed();

  assert.deepEqual(reporterCalls[1], [
    {
      clientTS: 1749124800000,
      name: "launchpad.item_launched",
      params: {
        app_id: "app-1",
        from_search: true,
        is_coming_soon: false,
        item_type: "app",
        provider: null
      }
    }
  ]);
  assert.deepEqual(reporterCalls[2], [
    {
      clientTS: 1749124800200,
      name: "launchpad.closed",
      params: {
        duration_ms: 200,
        item_launched: true
      }
    }
  ]);
});

test("workspace launchpad analytics tracks search and pagination", () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const analytics = createWorkspaceLaunchpadAnalyticsController({
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => 1749124800000
  });

  analytics.searched({
    queryLength: 5,
    resultCount: 3
  });
  analytics.pageChanged({
    pageIndex: 1,
    totalPages: 3
  });

  assert.deepEqual(reporterCalls, [
    [
      {
        clientTS: 1749124800000,
        name: "launchpad.searched",
        params: {
          query_length: 5,
          result_count: 3
        }
      }
    ],
    [
      {
        clientTS: 1749124800000,
        name: "launchpad.page_changed",
        params: {
          page_index: 1,
          total_pages: 3
        }
      }
    ]
  ]);
});

function createReporterService(calls: ReporterEventInput[][] = []) {
  return {
    async trackEvents(events: ReporterEventInput[]) {
      calls.push(events);
    }
  };
}
