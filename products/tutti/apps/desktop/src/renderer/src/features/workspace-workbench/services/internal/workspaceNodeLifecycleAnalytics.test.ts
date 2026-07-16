import assert from "node:assert/strict";
import test from "node:test";
import { BrowserClosedReporter } from "../../../analytics/reporters/browser-closed/browserClosedReporter.ts";
import { BrowserOpenedReporter } from "../../../analytics/reporters/browser-opened/browserOpenedReporter.ts";
import { createAnalyticsOpenedSourceParams } from "../../../analytics/reporters/openedSource.ts";
import type { ReporterEventInput } from "../../../analytics/services/reporterService.interface.ts";
import { createTrackedWorkbenchNodeLease } from "./workspaceNodeLifecycleAnalytics.ts";

test("tracked workbench node lease reports opened and closed duration", () => {
  const reporterCalls: ReporterEventInput[][] = [];
  let now = 1749124800000;
  const lease = createTrackedWorkbenchNodeLease({
    closedParams: ({ durationMs }) => ({ durationMs }),
    closedReporter: BrowserClosedReporter,
    openedParams: createAnalyticsOpenedSourceParams("restore"),
    openedReporter: BrowserOpenedReporter,
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => now
  });

  now = 1749124800310;
  lease?.release();

  assert.deepEqual(reporterCalls, [
    [
      {
        clientTS: 1749124800000,
        name: "browser.opened",
        params: {
          source: "restore",
          trigger: "automatic"
        }
      }
    ],
    [
      {
        clientTS: 1749124800310,
        name: "browser.closed",
        params: {
          duration_ms: 310
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
