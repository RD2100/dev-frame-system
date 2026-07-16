import assert from "node:assert/strict";
import test from "node:test";
import { resolveTerminalSurfaceScreenCachePlan } from "./terminalSurfaceScreenCachePlan.ts";

test("terminal surface screen cache plan saves serialized output when writes are settled", () => {
  assert.deepEqual(
    resolveTerminalSurfaceScreenCachePlan({
      hasPendingWrites: false,
      rawSnapshot: "raw",
      serialized: "serialized"
    }),
    {
      action: "save",
      rawSnapshot: "raw",
      serialized: "serialized"
    }
  );
});

test("terminal surface screen cache plan removes stale cache when writes are still pending", () => {
  assert.deepEqual(
    resolveTerminalSurfaceScreenCachePlan({
      hasPendingWrites: true,
      rawSnapshot: "raw",
      serialized: ""
    }),
    { action: "remove" }
  );
});

test("terminal surface screen cache plan skips empty settled snapshots", () => {
  assert.deepEqual(
    resolveTerminalSurfaceScreenCachePlan({
      hasPendingWrites: false,
      rawSnapshot: "raw",
      serialized: ""
    }),
    { action: "skip" }
  );
});
