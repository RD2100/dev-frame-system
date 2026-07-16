import assert from "node:assert/strict";
import test from "node:test";
import { resolveTerminalSurfaceResizePlan } from "./terminalSurfaceResizePlan.ts";

test("terminal surface resize plan emits the next size when dimensions change", () => {
  assert.deepEqual(
    resolveTerminalSurfaceResizePlan({
      lastSize: { cols: 80, rows: 24 },
      nextSize: { cols: 100, rows: 30 }
    }),
    { cols: 100, rows: 30 }
  );
});

test("terminal surface resize plan skips duplicate dimensions", () => {
  assert.equal(
    resolveTerminalSurfaceResizePlan({
      lastSize: { cols: 100, rows: 30 },
      nextSize: { cols: 100, rows: 30 }
    }),
    null
  );
});
