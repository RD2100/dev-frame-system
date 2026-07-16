import {
  resolveWorkspaceFileVisualKind as resolveWorkspaceFileManagerVisualKind,
  type WorkspaceFileVisualKind as WorkspaceFileManagerVisualKind
} from "@tutti-os/workspace-file-manager/services";

export type AgentWorkspaceFileVisualKind =
  | Exclude<WorkspaceFileManagerVisualKind, "directory">
  | "folder";

export function resolveAgentWorkspaceFileVisualKind(
  pathOrName: string,
  options: { refType?: string } = {}
): AgentWorkspaceFileVisualKind {
  const refType = options.refType;
  const kind = resolveWorkspaceFileManagerVisualKind({
    kind:
      refType === "folder" || refType === "directory" ? "directory" : "file",
    name: pathOrName,
    path: pathOrName
  });
  return kind === "directory" ? "folder" : kind;
}
