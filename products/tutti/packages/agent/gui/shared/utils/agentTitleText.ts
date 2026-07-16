const markdownLinkPattern = /\[((?:\\.|[^\]\\])*)\]\(([^)\s]+)\)/g;
const markdownLabelEscapePattern = /\\([\\[\]()])/g;

export function normalizeAgentTitleText(
  value: string | null | undefined
): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) {
    return "";
  }
  const normalized = trimmed.replace(markdownLinkPattern, (_, label: string) =>
    unescapeMarkdownLabel(label)
  );
  return normalized.replace(/\s+/g, " ").trim();
}

function unescapeMarkdownLabel(label: string): string {
  return label.replace(markdownLabelEscapePattern, "$1");
}
