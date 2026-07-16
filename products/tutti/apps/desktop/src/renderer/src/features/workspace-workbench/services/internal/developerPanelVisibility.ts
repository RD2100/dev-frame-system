const developerPanelVisibleStorageKey =
  "tutti.workspaceSettings.developerPanelVisible";

export interface DeveloperPanelVisibilityStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function resolveStorage(): DeveloperPanelVisibilityStorage | null {
  if (typeof globalThis.localStorage === "undefined") {
    return null;
  }
  return globalThis.localStorage;
}

export function readDeveloperPanelVisible(
  storage: DeveloperPanelVisibilityStorage | null = resolveStorage()
): boolean {
  try {
    return storage?.getItem(developerPanelVisibleStorageKey) === "1";
  } catch {
    return false;
  }
}

export function writeDeveloperPanelVisible(
  visible: boolean,
  storage: DeveloperPanelVisibilityStorage | null = resolveStorage()
): void {
  try {
    storage?.setItem(developerPanelVisibleStorageKey, visible ? "1" : "0");
  } catch {
    // Ignore persistence failures; keep the in-memory preference.
  }
}
