const hiddenWorkspaceAppIds = new Set<string>(["opencut"]);

export function shouldShowWorkspaceApp(appId: string): boolean {
  return !hiddenWorkspaceAppIds.has(appId.trim().toLowerCase());
}
