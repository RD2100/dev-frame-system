import assert from "node:assert/strict";
import test from "node:test";
import type { ReporterEventInput } from "../../../analytics/services/reporterService.interface.ts";
import {
  createTerminalAnalyticsDiagnostics,
  createTerminalSurfaceAnalytics,
  resolveTerminalOpenedParams
} from "./workspaceTerminalAnalytics.ts";

test("resolveTerminalOpenedParams reads launch trigger from activation payload", () => {
  assert.deepEqual(
    resolveTerminalOpenedParams({
      node: {
        data: {
          activation: {
            payload: {
              trigger: "launchpad"
            }
          }
        }
      }
    }),
    {
      source: "launchpad",
      trigger: "manual"
    }
  );
});

test("resolveTerminalOpenedParams falls back to restore", () => {
  assert.deepEqual(
    resolveTerminalOpenedParams({
      node: {
        data: {
          activation: null
        }
      }
    }),
    {
      source: "restore",
      trigger: "automatic"
    }
  );
});

test("terminal analytics reports opened from surface mount", () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const diagnostics = createTerminalAnalyticsDiagnostics({
    analytics: createAnalytics(reporterCalls),
    baseDiagnostics: createBaseDiagnostics()
  });

  diagnostics.log("mount", {
    nodeId: "workspace-terminal:session-1",
    sessionId: "session-1"
  });

  assert.equal(reporterCalls.length, 1);
  assert.deepEqual(reporterCalls[0], [
    {
      clientTS: reporterCalls[0]?.[0]?.clientTS,
      name: "terminal.opened",
      params: {
        source: "launchpad",
        trigger: "manual"
      }
    }
  ]);
});

test("terminal analytics suppresses strict mode remount duplicates", async () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const diagnostics = createTerminalAnalyticsDiagnostics({
    analytics: createAnalytics(reporterCalls, "dock"),
    baseDiagnostics: createBaseDiagnostics()
  });
  const nodeId = "workspace-terminal:session-1";
  const sessionId = "session-1";

  diagnostics.log("mount", { nodeId, sessionId });
  diagnostics.log("dispose", { nodeId, sessionId });
  diagnostics.log("mount", { nodeId, sessionId });

  await waitForTimers();

  assert.equal(reporterCalls.length, 1);
  assert.equal(reporterCalls[0]?.[0]?.name, "terminal.opened");
});

test("terminal analytics reports closed after final dispose", async () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const diagnostics = createTerminalAnalyticsDiagnostics({
    analytics: createAnalytics(reporterCalls),
    baseDiagnostics: createBaseDiagnostics()
  });
  const nodeId = "workspace-terminal:session-1";
  const sessionId = "session-1";

  diagnostics.log("mount", { nodeId, sessionId });
  diagnostics.log("dispose", { nodeId, sessionId });

  await waitForTimers();

  assert.equal(reporterCalls.length, 2);
  assert.equal(reporterCalls[0]?.[0]?.name, "terminal.opened");
  assert.equal(reporterCalls[1]?.[0]?.name, "terminal.closed");
  assert.equal(typeof reporterCalls[1]?.[0]?.params?.duration_ms, "number");
});

function createAnalytics(
  reporterCalls: ReporterEventInput[][],
  trigger: "dock" | "launchpad" = "launchpad"
) {
  const analytics = createTerminalSurfaceAnalytics({
    reporterService: createReporterService(reporterCalls)
  });
  analytics.observeNode({
    nodeId: "workspace-terminal:session-1",
    openedParams: {
      source: trigger,
      trigger: "manual"
    }
  });
  return analytics;
}

function createBaseDiagnostics() {
  return {
    log() {
      return undefined;
    }
  };
}

function createReporterService(calls: ReporterEventInput[][] = []) {
  return {
    async trackEvents(events: ReporterEventInput[]) {
      calls.push(events);
    }
  };
}

function waitForTimers() {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, 0);
  });
}
