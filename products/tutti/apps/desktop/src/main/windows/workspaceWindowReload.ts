export interface WorkspaceWindowReloadShortcutInput {
  alt: boolean;
  control: boolean;
  key: string;
  meta: boolean;
  shift: boolean;
  type: string;
}

export function isWorkspaceWindowReloadShortcut(
  input: WorkspaceWindowReloadShortcutInput
): boolean {
  if (input.type !== "keyDown" || input.alt) {
    return false;
  }

  const key = input.key.toLowerCase();
  if (key === "f5") {
    return true;
  }

  if (key !== "r") {
    return false;
  }

  return input.meta || input.control;
}

export interface WorkspaceWindowReloadShortcutEvent {
  preventDefault(): void;
}

export interface WorkspaceWindowReloadShortcutWebContents {
  devToolsWebContents?: WorkspaceWindowReloadShortcutInputSource | null;
  isDestroyed(): boolean;
  on(
    event: "before-input-event",
    listener: (
      event: WorkspaceWindowReloadShortcutEvent,
      input: WorkspaceWindowReloadShortcutInput
    ) => void
  ): void;
  on(event: "devtools-opened", listener: () => void): void;
  reloadIgnoringCache(): void;
}

export interface WorkspaceWindowReloadShortcutInputSource {
  on(
    event: "before-input-event",
    listener: (
      event: WorkspaceWindowReloadShortcutEvent,
      input: WorkspaceWindowReloadShortcutInput
    ) => void
  ): void;
}

export interface WorkspaceWindowReloadShortcutWindow {
  isDestroyed(): boolean;
  webContents: WorkspaceWindowReloadShortcutWebContents;
}

export function installWorkspaceWindowDevelopmentReloadShortcut(
  window: WorkspaceWindowReloadShortcutWindow,
  options: { enabled: boolean }
): void {
  const installReloadHandler = (
    source: WorkspaceWindowReloadShortcutInputSource
  ) => {
    source.on("before-input-event", (event, input) => {
      if (!isWorkspaceWindowReloadShortcut(input)) {
        return;
      }

      event.preventDefault();
      if (!options.enabled) {
        return;
      }
      if (window.isDestroyed() || window.webContents.isDestroyed()) {
        return;
      }

      window.webContents.reloadIgnoringCache();
    });
  };

  installReloadHandler(window.webContents);
  window.webContents.on("devtools-opened", () => {
    const devToolsContents = window.webContents.devToolsWebContents;
    if (!devToolsContents) {
      return;
    }

    installReloadHandler(devToolsContents);
  });
}
