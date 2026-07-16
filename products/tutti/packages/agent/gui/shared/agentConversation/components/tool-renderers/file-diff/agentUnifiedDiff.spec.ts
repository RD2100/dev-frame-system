import { describe, expect, it } from "vitest";
import {
  parseAgentUnifiedDiff,
  parseAgentUnifiedDiffLines,
  parseAgentUnifiedDiffStats
} from "./agentUnifiedDiff";

describe("agentUnifiedDiff", () => {
  const diffText = [
    "diff --git a/src/a.ts b/src/a.ts",
    "index 1111111..2222222 100644",
    "--- a/src/a.ts",
    "+++ b/src/a.ts",
    "@@ -1,2 +1,2 @@",
    "-const ready = false",
    "+const ready = true",
    " export const value = 1"
  ].join("\n");

  it("parses unified diff into old/new strings", () => {
    expect(parseAgentUnifiedDiff(diffText)).toEqual({
      oldString: "const ready = false\nexport const value = 1",
      newString: "const ready = true\nexport const value = 1"
    });
  });

  it("parses added/removed diff stats", () => {
    expect(parseAgentUnifiedDiffStats(diffText)).toEqual({
      added: 1,
      removed: 1
    });
  });

  it("parses unified diff into numbered display lines", () => {
    expect(parseAgentUnifiedDiffLines(diffText)).toEqual([
      {
        kind: "remove",
        oldLineNumber: 1,
        newLineNumber: null,
        text: "const ready = false"
      },
      {
        kind: "add",
        oldLineNumber: null,
        newLineNumber: 1,
        text: "const ready = true"
      },
      {
        kind: "context",
        oldLineNumber: 2,
        newLineNumber: 2,
        text: "export const value = 1"
      }
    ]);
  });

  it("parses deleted git diff stats", () => {
    const deletedDiff = [
      "diff --git a/a.md b/a.md",
      "deleted file mode 100644",
      "--- a/a.md",
      "+++ /dev/null",
      "@@ -1 +0,0 @@",
      "-aaaaa"
    ].join("\n");

    expect(parseAgentUnifiedDiffStats(deletedDiff)).toEqual({
      added: 0,
      removed: 1
    });
  });

  it("parses deleted apply_patch stats", () => {
    const deletedPatch = [
      "*** Begin Patch",
      "*** Delete File: a.md",
      "@@",
      "-aaaaa",
      "*** End Patch"
    ].join("\n");

    expect(parseAgentUnifiedDiffStats(deletedPatch)).toEqual({
      added: 0,
      removed: 1
    });
  });

  it("handles escaped newline JSON payload wrappers", () => {
    const wrapped = JSON.stringify({ content: diffText.replace(/\n/g, "\\n") });
    expect(parseAgentUnifiedDiff(wrapped)).toEqual({
      oldString: "const ready = false\nexport const value = 1",
      newString: "const ready = true\nexport const value = 1"
    });
  });
});
