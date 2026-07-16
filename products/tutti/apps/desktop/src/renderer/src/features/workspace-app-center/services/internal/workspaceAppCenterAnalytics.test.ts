import assert from "node:assert/strict";
import test from "node:test";
import type { ReporterEventInput } from "@renderer/features/analytics";
import { createWorkspaceAppCenterOpenedLease } from "./workspaceAppCenterAnalytics.ts";

test("workspace app center opened lease tracks exactly one opened event", () => {
  const reporterCalls: ReporterEventInput[][] = [];

  const lease = createWorkspaceAppCenterOpenedLease({
    reporterService: createReporterService(reporterCalls)
  });

  assert.ok(lease);
  assert.equal(reporterCalls.length, 1);
  assert.deepEqual(reporterCalls[0], [
    {
      clientTS: reporterCalls[0]?.[0]?.clientTS,
      name: "app_center.opened",
      params: {}
    }
  ]);

  lease?.release();
});

function createReporterService(calls: ReporterEventInput[][] = []) {
  return {
    async trackEvents(events: ReporterEventInput[]) {
      calls.push(events);
    }
  };
}
