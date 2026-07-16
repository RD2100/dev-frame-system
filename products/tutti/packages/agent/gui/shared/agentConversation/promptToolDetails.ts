import { extractAgentMcpToolTarget } from "../agentMcpToolTarget";

export interface PromptToolDetail {
  kind: "command" | "mcp" | "path" | "query";
  value: string;
  meta?: string;
}

export function getPromptToolDetails(
  input: Record<string, unknown> | null
): PromptToolDetail[] {
  if (!input) {
    return [];
  }
  const mcpTarget = extractAgentMcpToolTarget({ input });
  const mcpDetails: PromptToolDetail[] = mcpTarget
    ? [
        {
          kind: "mcp",
          value: mcpTarget.displayName,
          ...(mcpTarget.instruction ? { meta: mcpTarget.instruction } : {})
        }
      ]
    : [];
  const detailInput = resolveToolDetailInput(input);
  const command =
    commandStringValue(detailInput.command) ??
    commandStringValue(detailInput.cmd);
  if (command) {
    return [
      ...mcpDetails,
      {
        kind: "command",
        value: command,
        ...(stringValue(detailInput.description)
          ? { meta: stringValue(detailInput.description) as string }
          : {})
      }
    ];
  }
  const filePath =
    stringValue(detailInput.file_path) ??
    stringValue(detailInput.filePath) ??
    stringValue(detailInput.path) ??
    stringValue(detailInput.notebook_path);
  if (filePath) {
    const lineRange = formatLineRange(detailInput);
    return [
      ...mcpDetails,
      {
        kind: "path",
        value: filePath,
        ...(lineRange ? { meta: lineRange } : {})
      }
    ];
  }
  const query =
    stringValue(detailInput.query) ??
    stringValue(detailInput.search_query) ??
    stringValue(detailInput.searchQuery) ??
    stringValue(detailInput.pattern);
  if (query) {
    return [
      ...mcpDetails,
      {
        kind: "query",
        value: query
      }
    ];
  }
  return mcpDetails;
}

export function isPromptRequestIdTitle(value: string): boolean {
  return /^requestid\s*:/iu.test(value.trim());
}

function resolveToolDetailInput(
  input: Record<string, unknown>
): Record<string, unknown> {
  const toolCall = objectValue(input.toolCall);
  return (
    firstObjectValue(input, [
      "command",
      "cmd",
      "file_path",
      "filePath",
      "path",
      "notebook_path",
      "query",
      "search_query",
      "searchQuery",
      "pattern"
    ]) ??
    firstObjectValue(toolCall, [
      "input",
      "rawInput",
      "raw_input",
      "arguments",
      "args"
    ]) ??
    toolCall ??
    input
  );
}

function firstObjectValue(
  input: Record<string, unknown> | null,
  keys: readonly string[]
): Record<string, unknown> | null {
  if (!input) {
    return null;
  }
  if (keys.some((key) => stringValue(input[key]))) {
    return input;
  }
  for (const key of keys) {
    const value = objectValue(input[key]);
    if (value) {
      return value;
    }
  }
  return null;
}

function formatLineRange(input: Record<string, unknown>): string | null {
  const start = numericValue(input.startLine) ?? numericValue(input.start_line);
  const end = numericValue(input.endLine) ?? numericValue(input.end_line);
  if (start === null || end === null) {
    return null;
  }
  return start === end ? `L${start}` : `L${start}-${end}`;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function commandStringValue(value: unknown): string | null {
  if (typeof value === "string") {
    return stringValue(value);
  }
  if (!Array.isArray(value)) {
    return null;
  }
  const shellFlag = stringValue(value[value.length - 2]);
  const shellCommand = stringValue(value[value.length - 1]);
  if ((shellFlag === "-c" || shellFlag === "-lc") && shellCommand) {
    return shellCommand;
  }
  const parts = value.flatMap((part) => {
    const text = stringValue(part);
    return text ? [text] : [];
  });
  return parts.length > 0 ? parts.join(" ") : null;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function numericValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
