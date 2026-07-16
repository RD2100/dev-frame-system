import assert from "node:assert/strict";
import test from "node:test";
import { resolveTerminalSurfaceOutputPlan } from "./terminalSurfaceOutputPlan.ts";

test("terminal surface output plan skips stale empty bootstrap over cached output", () => {
  assert.equal(
    resolveTerminalSurfaceOutputPlan({
      committedRawOutput: "cached output",
      contentEpoch: 0,
      nextContentEpoch: 0,
      rawOutput: ""
    }),
    null
  );
});

test("terminal surface output plan resets on content epoch changes", () => {
  assert.deepEqual(
    resolveTerminalSurfaceOutputPlan({
      committedRawOutput: "before",
      contentEpoch: 1,
      nextContentEpoch: 2,
      rawOutput: "after"
    }),
    {
      nextCommittedRawOutput: "after",
      nextContentEpoch: 2,
      reset: true,
      write: "after"
    }
  );
});

test("terminal surface output plan appends only the delta for incremental output", () => {
  assert.deepEqual(
    resolveTerminalSurfaceOutputPlan({
      committedRawOutput: "hello",
      contentEpoch: 2,
      nextContentEpoch: 2,
      rawOutput: "hello world"
    }),
    {
      nextCommittedRawOutput: "hello world",
      nextContentEpoch: 2,
      reset: false,
      write: " world"
    }
  );
});

test("terminal surface output plan falls back to reset when delta cannot be derived", () => {
  assert.deepEqual(
    resolveTerminalSurfaceOutputPlan({
      committedRawOutput: "alpha-beta",
      contentEpoch: 2,
      nextContentEpoch: 2,
      rawOutput: "beta"
    }),
    {
      nextCommittedRawOutput: "beta",
      nextContentEpoch: 2,
      reset: true,
      write: "beta"
    }
  );
});
