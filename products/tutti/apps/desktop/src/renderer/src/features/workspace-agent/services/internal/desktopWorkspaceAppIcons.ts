import type { WorkspaceAppCenterApp } from "@tutti-os/workspace-app-center";
import {
  resolveDesktopWorkspaceAppDefaultIconUrl,
  SEEDED_DESKTOP_WORKSPACE_APP_ICON_IDS
} from "../../../../../../shared/workspaceAppIconDefaults.ts";

export interface DesktopWorkspaceAppIconEntry {
  appId: string;
  iconUrl: string;
  workspaceId: string;
}

type DesktopWorkspaceAppIconSource = Pick<
  WorkspaceAppCenterApp,
  "appId" | "availableIconUrl" | "iconUrl"
>;

export function resolveDesktopWorkspaceAppIconEntries(input: {
  apps: readonly DesktopWorkspaceAppIconSource[];
  workspaceId: string;
}): DesktopWorkspaceAppIconEntry[] {
  const entriesByKey = new Map<string, DesktopWorkspaceAppIconEntry>();
  for (const app of input.apps) {
    addWorkspaceAppIconEntry(entriesByKey, {
      appId: app.appId,
      iconUrl: app.iconUrl ?? app.availableIconUrl ?? null,
      workspaceId: input.workspaceId
    });
  }
  for (const appId of SEEDED_DESKTOP_WORKSPACE_APP_ICON_IDS) {
    if (entriesByKey.has(workspaceAppIconEntryKey(appId, input.workspaceId))) {
      continue;
    }
    const iconUrl = resolveDesktopWorkspaceAppDefaultIconUrl(appId);
    if (!iconUrl) {
      continue;
    }
    addWorkspaceAppIconEntry(entriesByKey, {
      appId,
      iconUrl,
      workspaceId: input.workspaceId
    });
  }
  return [...entriesByKey.values()];
}

function addWorkspaceAppIconEntry(
  entriesByKey: Map<string, DesktopWorkspaceAppIconEntry>,
  input: {
    appId: string | null | undefined;
    iconUrl: string | null | undefined;
    workspaceId: string;
  }
): void {
  const appId = input.appId?.trim() ?? "";
  const iconUrl = input.iconUrl?.trim() ?? "";
  if (!appId || !iconUrl) {
    return;
  }
  entriesByKey.set(workspaceAppIconEntryKey(appId, input.workspaceId), {
    appId,
    iconUrl,
    workspaceId: input.workspaceId
  });
}

function workspaceAppIconEntryKey(appId: string, workspaceId: string): string {
  return `${workspaceId}\u0000${appId.trim()}`;
}
