import assert from "node:assert/strict";
import test from "node:test";
import { createWindowCloseRequestTracker } from "./windowCloseRequestTracker.ts";

test("window close request tracker flips closing state synchronously", () => {
  const tracker = createWindowCloseRequestTracker();

  assert.equal(tracker.isClosing, false);

  tracker.begin();

  assert.equal(tracker.isClosing, true);

  tracker.finish();

  assert.equal(tracker.isClosing, false);
});
