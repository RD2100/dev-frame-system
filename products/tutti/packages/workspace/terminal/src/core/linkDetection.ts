import type { TerminalLinkTarget } from "../contracts/index.ts";

export interface DetectedTerminalFileLink {
  column?: number;
  index: number;
  line?: number;
  path: string;
  text: string;
}

const pathCandidatePattern =
  /(?<path>(?:~|\.{1,2}|\/)[^\s"'`<>|:([\]]+|[A-Za-z0-9_.-]+\/[^\s"'`<>|:([\]]+)(?<suffix>(?::(?<lineColon>\d+)(?::(?<columnColon>\d+))?)|(?:\((?<lineParen>\d+)(?:,\s*(?<columnParen>\d+))?\))|(?:\[(?<lineBracket>\d+)(?:,\s*(?<columnBracket>\d+))?\]))?/g;

export function detectTerminalFileLinks(
  text: string
): DetectedTerminalFileLink[] {
  const links: DetectedTerminalFileLink[] = [];
  pathCandidatePattern.lastIndex = 0;

  let match = pathCandidatePattern.exec(text);
  while (match) {
    const groups = match.groups ?? {};
    const rawPath = groups.path ?? "";
    const suffix = groups.suffix ?? "";
    const candidateText = `${rawPath}${suffix}`;
    const trimmed = trimTerminalPathCandidate(rawPath);
    const trimAmount = rawPath.length - trimmed.length;

    if (isTerminalPathCandidate(trimmed, text, match.index)) {
      const line = parsePositiveInteger(
        groups.lineColon ?? groups.lineParen ?? groups.lineBracket
      );
      const column = parsePositiveInteger(
        groups.columnColon ?? groups.columnParen ?? groups.columnBracket
      );
      links.push({
        column,
        index: match.index,
        line,
        path: trimmed,
        text: candidateText.slice(0, candidateText.length - trimAmount)
      });
    }

    match = pathCandidatePattern.exec(text);
  }

  return links;
}

export function toTerminalLinkTarget(
  link: DetectedTerminalFileLink
): TerminalLinkTarget {
  return {
    column: link.column,
    line: link.line,
    path: link.path
  };
}

function trimTerminalPathCandidate(value: string): string {
  let result = value.trim();
  while (/[),.;:!?]$/.test(result) && !looksLikeFileExtension(result)) {
    result = result.slice(0, -1);
  }
  return result;
}

function looksLikeFileExtension(value: string): boolean {
  return /\.[A-Za-z0-9]{1,8}$/.test(value);
}

function isTerminalPathCandidate(
  value: string,
  sourceText: string,
  index: number
): boolean {
  if (value.length === 0) {
    return false;
  }
  if (/^\d+(?::\d+)*$/.test(value)) {
    return false;
  }
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) {
    return false;
  }
  if (value.startsWith("//") || sourceText[index - 1] === ":") {
    return false;
  }
  if (value.startsWith("node:")) {
    return false;
  }
  return (
    value.startsWith("/") ||
    value.startsWith("./") ||
    value.startsWith("../") ||
    value.startsWith("~/") ||
    value.includes("/")
  );
}

function parsePositiveInteger(value: string | undefined): number | undefined {
  if (!value) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}
