import { join } from "node:path";

export function resolvePackagedWorkspaceRendererIndexPath(
  appPath: string
): string {
  return join(appPath, "out", "renderer", "index.html");
}
