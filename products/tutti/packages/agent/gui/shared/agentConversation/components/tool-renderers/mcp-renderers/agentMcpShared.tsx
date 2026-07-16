import type { AgentToolCallVM } from "../../../contracts/agentToolCallVM";
import { extractAgentMcpToolTarget } from "../../../../agentMcpToolTarget";
import {
  arrayValue,
  objectValue,
  stringValue
} from "../agentToolContentShared";

export interface AgentMcpNormalizedPayload {
  server: string | null;
  tool: string | null;
  inputSummary: string | null;
  structured: unknown;
  text: string | null;
}

export function normalizeMcpPayload(
  call: AgentToolCallVM
): AgentMcpNormalizedPayload {
  const target = extractAgentMcpToolTarget({
    input: call.input,
    metadata: call.metadata,
    payload: call.payload,
    toolName: call.toolName,
    name: call.name
  });
  const server =
    target?.server ??
    stringValue(call.metadata?.server) ??
    stringValue(call.metadata?.serverName) ??
    stringValue(call.metadata?.mcpServer) ??
    null;
  const tool =
    target?.tool ??
    stringValue(call.metadata?.tool) ??
    stringValue(call.metadata?.toolName) ??
    call.toolName;

  const structured = firstStructuredValue(
    call.output?.structuredContent,
    parseJsonString(call.output?.content),
    parseJsonString(call.output?.output),
    parseJsonString(call.output?.stdout)
  );

  return {
    server,
    tool,
    inputSummary: firstString(
      stringValue(call.input?.query),
      stringValue(call.input?.url),
      stringValue(call.input?.path),
      stringValue(call.input?.prompt),
      stringValue(call.input?.command)
    ),
    structured,
    text: firstString(
      contentArrayText(call.output?.content),
      stringValue(call.output?.content),
      stringValue(call.output?.output),
      stringValue(call.output?.stdout)
    )
  };
}

export function parsedItems(value: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(value)) {
    return value.flatMap((entry) => {
      const record = objectValue(entry);
      return record ? [record] : [];
    });
  }
  const record = objectValue(value);
  if (!record) {
    return [];
  }
  const candidateArrays = [
    arrayValue(record.issues),
    arrayValue(record.pages),
    arrayValue(record.results),
    arrayValue(record.resources),
    arrayValue(record.documents),
    arrayValue(record.docs),
    arrayValue(record.items)
  ];
  for (const candidate of candidateArrays) {
    if (candidate && candidate.length > 0) {
      return candidate.flatMap((entry) => {
        const item = objectValue(entry);
        return item ? [item] : [];
      });
    }
  }
  return [];
}

export function itemPrimaryText(item: Record<string, unknown>): string | null {
  return firstString(
    stringValue(item.key),
    stringValue(item.title),
    stringValue(item.name),
    stringValue(item.path),
    stringValue(item.url),
    stringValue(item.id)
  );
}

export function itemSecondaryText(
  item: Record<string, unknown>
): string | null {
  return firstString(
    stringValue(item.summary),
    stringValue(item.description),
    stringValue(item.status),
    stringValue(item.type)
  );
}

function firstStructuredValue(...values: unknown[]): unknown {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value;
    }
    if (value && typeof value === "object") {
      return value;
    }
  }
  return null;
}

function parseJsonString(value: unknown): unknown {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function contentArrayText(value: unknown): string | null {
  const items = arrayValue(value);
  if (!items) {
    return null;
  }
  const text = items
    .flatMap((entry) => {
      const record = objectValue(entry);
      if (!record) {
        return [];
      }
      return [
        firstString(
          stringValue(record.text),
          stringValue(record.content),
          stringValue(objectValue(record.content)?.text)
        )
      ].filter((candidate): candidate is string => Boolean(candidate));
    })
    .join("\n")
    .trim();
  return text || null;
}

function firstString(...values: Array<string | null>): string | null {
  for (const value of values) {
    if (value) {
      return value;
    }
  }
  return null;
}
