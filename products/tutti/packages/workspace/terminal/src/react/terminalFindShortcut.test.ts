import assert from "node:assert/strict";
import test from "node:test";
import { isTerminalFindShortcut } from "./terminalFindShortcut.ts";

test("terminal find shortcut accepts cmd+f and ctrl+f", () => {
  assert.equal(
    isTerminalFindShortcut({
      altKey: false,
      ctrlKey: false,
      key: "f",
      metaKey: true
    }),
    true
  );
  assert.equal(
    isTerminalFindShortcut({
      altKey: false,
      ctrlKey: true,
      key: "F",
      metaKey: false
    }),
    true
  );
});

test("terminal find shortcut rejects unrelated modifier combinations", () => {
  assert.equal(
    isTerminalFindShortcut({
      altKey: true,
      ctrlKey: false,
      key: "f",
      metaKey: true
    }),
    false
  );
  assert.equal(
    isTerminalFindShortcut({
      altKey: false,
      ctrlKey: false,
      key: "f",
      metaKey: false
    }),
    false
  );
  assert.equal(
    isTerminalFindShortcut({
      altKey: false,
      ctrlKey: true,
      key: "g",
      metaKey: false
    }),
    false
  );
});
