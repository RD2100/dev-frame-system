export function validateWorkspaceFileEntryName(
  name: string
): "invalid" | "required" | null {
  const trimmed = name.trim();
  if (!trimmed) {
    return "required";
  }
  if (
    trimmed.includes("/") ||
    trimmed.includes("\\") ||
    trimmed === "." ||
    trimmed === ".."
  ) {
    return "invalid";
  }
  return null;
}
