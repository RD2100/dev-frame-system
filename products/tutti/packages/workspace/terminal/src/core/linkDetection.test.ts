import assert from "node:assert/strict";
import test from "node:test";
import { detectTerminalFileLinks } from "./linkDetection.ts";

test("detectTerminalFileLinks detects absolute and relative paths with locations", () => {
  assert.deepEqual(
    detectTerminalFileLinks(
      "src/main.ts:12:4 /tmp/demo.txt ./pkg/index.ts(9, 2)"
    ).map(({ column, line, path, text }) => ({ column, line, path, text })),
    [
      {
        column: 4,
        line: 12,
        path: "src/main.ts",
        text: "src/main.ts:12:4"
      },
      {
        column: undefined,
        line: undefined,
        path: "/tmp/demo.txt",
        text: "/tmp/demo.txt"
      },
      {
        column: 2,
        line: 9,
        path: "./pkg/index.ts",
        text: "./pkg/index.ts(9, 2)"
      }
    ]
  );
});

test("detectTerminalFileLinks skips urls and pure numeric locations", () => {
  assert.deepEqual(
    detectTerminalFileLinks(
      "https://example.com/a/b 10:20 ~/project/file.md[7]"
    ).map(({ line, path, text }) => ({ line, path, text })),
    [
      {
        line: 7,
        path: "~/project/file.md",
        text: "~/project/file.md[7]"
      }
    ]
  );
});
