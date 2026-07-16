import assert from "node:assert/strict";
import test from "node:test";
import { resolveInitialTerminalDimensions } from "./dimensions.ts";

test("resolveInitialTerminalDimensions floors valid dimensions", () => {
  assert.deepEqual(
    resolveInitialTerminalDimensions({
      cols: 120.8,
      rows: 33.2
    }),
    {
      cols: 120,
      rows: 33
    }
  );
});

test("resolveInitialTerminalDimensions rejects missing or invalid dimensions", () => {
  assert.equal(resolveInitialTerminalDimensions(null), null);
  assert.equal(resolveInitialTerminalDimensions({ cols: 80, rows: 0 }), null);
  assert.equal(
    resolveInitialTerminalDimensions({ cols: Number.NaN, rows: 24 }),
    null
  );
});
