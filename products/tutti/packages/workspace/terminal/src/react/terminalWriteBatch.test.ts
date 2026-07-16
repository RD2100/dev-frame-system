import assert from "node:assert/strict";
import test from "node:test";
import { drainTerminalWriteBatch } from "./terminalWriteBatch.ts";

test("terminal write batch drains whole chunks up to the limit", () => {
  assert.deepEqual(drainTerminalWriteBatch(["abc", "def", "ghi"], 6), {
    nextWrite: "abcdef",
    remainingChunks: ["ghi"]
  });
});

test("terminal write batch splits oversized chunks and preserves the remainder", () => {
  assert.deepEqual(drainTerminalWriteBatch(["abcdef"], 4), {
    nextWrite: "abcd",
    remainingChunks: ["ef"]
  });
});
