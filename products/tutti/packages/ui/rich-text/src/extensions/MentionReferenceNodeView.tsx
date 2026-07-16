import type { JSX } from "react";
import { NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import {
  MentionPill,
  type MentionPillKind
} from "@tutti-os/ui-system/components";

const richTextMentionReferencePillClassName = "max-w-[16rem]";

function readStringAttr(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readMentionPresentationUrl(presentation: unknown): string | null {
  if (!presentation || typeof presentation !== "object") {
    return null;
  }
  const value =
    (presentation as { iconUrl?: unknown; thumbnailUrl?: unknown }).iconUrl ??
    (presentation as { thumbnailUrl?: unknown }).thumbnailUrl;
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}

// 句柄类 mention(如 workspace-reference 项目引用)的图标随 href 的 scope 编码,
// markdown 带不了 presentation,故回退读 scope.icon,使 chip 与 agent 一样显示来源图标。
function readMentionScopeValue(scope: unknown, key: string): string {
  if (!scope || typeof scope !== "object") {
    return "";
  }
  return readStringAttr((scope as Record<string, unknown>)[key]);
}

// providerId(+ workspace-reference 的 source)映射到设计系统 MentionPill 的 kind,
// 让颜色/图标与 agent GUI 的 mention chip 完全一致。
function resolveMentionPillKind(
  providerId: string,
  scope: unknown
): MentionPillKind {
  const id = providerId.trim();
  if (id === "agent-session" || id === "session") {
    return "session";
  }
  if (id === "workspace-app") {
    return "app";
  }
  if (id === "workspace-issue") {
    return "issue";
  }
  if (id === "workspace-reference") {
    return readMentionScopeValue(scope, "source") === "task" ? "issue" : "app";
  }
  if (id === "file") {
    return "file";
  }
  return "issue";
}

export function MentionReferenceNodeView({
  node,
  selected
}: NodeViewProps): JSX.Element {
  const label =
    typeof node.attrs.label === "string"
      ? node.attrs.label.trim().replace(/^@+/, "").trim()
      : "";
  const iconUrl =
    readMentionPresentationUrl(node.attrs.presentation) ||
    readMentionScopeValue(node.attrs.scope, "icon");
  const kind = resolveMentionPillKind(
    readStringAttr(node.attrs.providerId),
    node.attrs.scope
  );

  return (
    <NodeViewWrapper
      as="span"
      className={`inline-flex max-w-full align-baseline${
        selected ? " is-selected" : ""
      }`}
      contentEditable={false}
      data-rich-text-mention-reference="true"
    >
      <MentionPill
        className={richTextMentionReferencePillClassName}
        iconUrl={iconUrl || undefined}
        kind={kind}
        label={label}
        removable={false}
      />
    </NodeViewWrapper>
  );
}
