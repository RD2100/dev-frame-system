import {
  extractAgentPatchPath,
  inferAgentPatchChangeType,
  normalizeAgentPatchText,
  type AgentPatchChangeType
} from "../../../rules/agentPatchMetadata";

export { extractAgentPatchPath, inferAgentPatchChangeType };
export type AgentUnifiedDiffChangeType = AgentPatchChangeType;

export interface ParsedAgentUnifiedDiff {
  oldString: string;
  newString: string;
}

export interface ParsedAgentUnifiedDiffLine {
  kind: "add" | "remove" | "context";
  oldLineNumber: number | null;
  newLineNumber: number | null;
  text: string;
}

const DIFF_META_PREFIXES = [
  "diff --git ",
  "index ",
  "--- ",
  "+++ ",
  "*** "
] as const;

export function parseAgentUnifiedDiff(
  diffText: string
): ParsedAgentUnifiedDiff | null {
  if (!diffText.trim()) {
    return null;
  }

  const normalizedText = normalizeAgentPatchText(diffText);
  const oldLines: string[] = [];
  const newLines: string[] = [];
  let sawChangeLine = false;
  let sawHunkHeader = false;

  for (const line of normalizedText.replace(/\r\n/g, "\n").split("\n")) {
    if (line.startsWith("@@")) {
      if (sawHunkHeader && (oldLines.length > 0 || newLines.length > 0)) {
        oldLines.push("");
        newLines.push("");
      }
      sawHunkHeader = true;
      continue;
    }
    if (DIFF_META_PREFIXES.some((prefix) => line.startsWith(prefix))) {
      continue;
    }
    if (line === "\\ No newline at end of file") {
      continue;
    }
    if (line.startsWith("+")) {
      newLines.push(line.slice(1));
      sawChangeLine = true;
      continue;
    }
    if (line.startsWith("-")) {
      oldLines.push(line.slice(1));
      sawChangeLine = true;
      continue;
    }
    if (line.startsWith(" ")) {
      const content = line.slice(1);
      oldLines.push(content);
      newLines.push(content);
    }
  }

  if (!sawChangeLine) {
    return null;
  }

  return {
    oldString: oldLines.join("\n"),
    newString: newLines.join("\n")
  };
}

export function parseAgentUnifiedDiffLines(
  diffText: string
): ParsedAgentUnifiedDiffLine[] {
  const normalized = normalizeAgentPatchText(diffText);
  if (!normalized.trim()) {
    return [];
  }

  const lines: ParsedAgentUnifiedDiffLine[] = [];
  let oldLineNumber = 0;
  let newLineNumber = 0;

  for (const line of normalized.replace(/\r\n/g, "\n").split("\n")) {
    if (line.startsWith("@@")) {
      const match = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (!match) {
        continue;
      }
      oldLineNumber = Number.parseInt(match[1] ?? "0", 10);
      newLineNumber = Number.parseInt(match[2] ?? "0", 10);
      continue;
    }
    if (DIFF_META_PREFIXES.some((prefix) => line.startsWith(prefix))) {
      continue;
    }
    if (line === "\\ No newline at end of file") {
      continue;
    }
    if (line.startsWith("+")) {
      lines.push({
        kind: "add",
        oldLineNumber: null,
        newLineNumber,
        text: line.slice(1)
      });
      newLineNumber += 1;
      continue;
    }
    if (line.startsWith("-")) {
      lines.push({
        kind: "remove",
        oldLineNumber,
        newLineNumber: null,
        text: line.slice(1)
      });
      oldLineNumber += 1;
      continue;
    }
    if (line.startsWith(" ")) {
      lines.push({
        kind: "context",
        oldLineNumber,
        newLineNumber,
        text: line.slice(1)
      });
      oldLineNumber += 1;
      newLineNumber += 1;
    }
  }

  return lines;
}

export function parseAgentUnifiedDiffStats(diffText: string): {
  added: number;
  removed: number;
} {
  let added = 0;
  let removed = 0;
  for (const line of normalizeAgentPatchText(diffText)
    .replace(/\r\n/g, "\n")
    .split("\n")) {
    if (line.startsWith("+++") || line.startsWith("---")) {
      continue;
    }
    if (line.startsWith("+")) {
      added += 1;
      continue;
    }
    if (line.startsWith("-")) {
      removed += 1;
    }
  }
  return { added, removed };
}
