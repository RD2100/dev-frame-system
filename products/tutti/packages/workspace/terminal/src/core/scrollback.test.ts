import assert from "node:assert/strict";
import test from "node:test";
import {
  mergeTerminalScrollbackSnapshots,
  resolveTerminalScrollbackDelta,
  truncateTerminalScrollback
} from "./scrollback.ts";
import { resolveSuffixPrefixOverlap } from "./stringOverlap.ts";

test("resolveSuffixPrefixOverlap finds the longest suffix/prefix match", () => {
  assert.equal(resolveSuffixPrefixOverlap("abc123", "123def"), 3);
  assert.equal(resolveSuffixPrefixOverlap("abc", "def"), 0);
  assert.equal(resolveSuffixPrefixOverlap("", "def"), 0);
});

test("resolveTerminalScrollbackDelta returns only newly appended output", () => {
  assert.equal(resolveTerminalScrollbackDelta("hello\nwor", "world\n"), "ld\n");
  assert.equal(resolveTerminalScrollbackDelta("same", "same"), "");
  assert.equal(resolveTerminalScrollbackDelta("", "first"), "first");
});

test("mergeTerminalScrollbackSnapshots deduplicates overlapping snapshots", () => {
  assert.equal(
    mergeTerminalScrollbackSnapshots("alpha\nbeta\n", "beta\ngamma\n"),
    "alpha\nbeta\ngamma\n"
  );
  assert.equal(mergeTerminalScrollbackSnapshots("abc", "abcdef"), "abcdef");
  assert.equal(mergeTerminalScrollbackSnapshots("abcdef", "abc"), "abcdef");
});

test("truncateTerminalScrollback keeps the newest content", () => {
  assert.equal(truncateTerminalScrollback("abcdef", { maxChars: 3 }), "def");
});
