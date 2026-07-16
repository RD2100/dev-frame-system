import assert from "node:assert/strict";
import test from "node:test";
import { hasTerminalHeaderDefaultActions } from "./headerActions.ts";

test("header actions helper treats nullish values as absent", () => {
  assert.equal(hasTerminalHeaderDefaultActions(undefined), false);
  assert.equal(hasTerminalHeaderDefaultActions(null), false);
});

test("header actions helper treats provided actions as present", () => {
  assert.equal(hasTerminalHeaderDefaultActions("close"), true);
  assert.equal(hasTerminalHeaderDefaultActions(0), true);
});
