import assert from "node:assert/strict";
import test from "node:test";
import type { ReporterEventInput } from "../../services/reporterService.interface.ts";
import { WorkspaceOpenedReporter } from "./workspaceOpenedReporter.ts";

test("workspace opened reporter emits the spec event with snake case params", async () => {
  const calls: ReporterEventInput[][] = [];
  const reporter = new WorkspaceOpenedReporter(
    {
      routeView: "workspace"
    },
    {
      reporterService: {
        async trackEvents(events) {
          calls.push(events);
        }
      },
      now: () => 1749124800000
    }
  );

  await reporter.report();

  assert.deepEqual(calls, [
    [
      {
        clientTS: 1749124800000,
        name: "workspace.opened",
        params: {
          route_view: "workspace"
        }
      }
    ]
  ]);
});
