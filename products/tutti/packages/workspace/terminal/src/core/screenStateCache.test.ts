import assert from "node:assert/strict";
import test from "node:test";
import { createTerminalScreenStateCache } from "./screenStateCache.ts";

test("terminal screen cache returns state only for matching node and session", () => {
  const cache = createTerminalScreenStateCache();

  cache.set(" node-1 ", {
    cols: 80.7,
    rawSnapshot: "raw",
    rows: 24.2,
    serialized: "screen",
    sessionId: " session-1 "
  });

  assert.deepEqual(cache.get("node-1", "session-1"), {
    cols: 80,
    rawSnapshot: "raw",
    rows: 24,
    serialized: "screen",
    sessionId: "session-1"
  });
  assert.equal(cache.get("node-1", "session-2"), null);
});

test("terminal screen cache invalidation blocks stale writes once", () => {
  const cache = createTerminalScreenStateCache();

  cache.set("node-1", {
    cols: 80,
    rawSnapshot: "raw",
    rows: 24,
    serialized: "screen",
    sessionId: "session-1"
  });
  cache.invalidate("node-1", "session-1");

  assert.equal(cache.isInvalidated("node-1", "session-1"), true);
  assert.equal(cache.get("node-1", "session-1"), null);

  cache.set("node-1", {
    cols: 80,
    rawSnapshot: "late",
    rows: 24,
    serialized: "late-screen",
    sessionId: "session-1"
  });

  assert.equal(cache.isInvalidated("node-1", "session-1"), false);
  assert.equal(cache.get("node-1", "session-1"), null);
});
