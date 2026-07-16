export interface DesktopNotificationActivationWindow {
  focus(): void;
  isDestroyed(): boolean;
  isMinimized(): boolean;
  restore(): void;
  show(): void;
}

export interface DesktopNotificationActivationDependencies {
  focusApp(): void;
  getWindows(): DesktopNotificationActivationWindow[];
  onOpenStartupWindowFailed?: (error: unknown) => void;
  openStartupWindow(): Promise<void>;
}

export interface DesktopNotificationActivation {
  activate(): Promise<void>;
}

export function createDesktopNotificationActivation(
  dependencies: DesktopNotificationActivationDependencies
): DesktopNotificationActivation {
  return {
    async activate() {
      dependencies.focusApp();
      const window = dependencies
        .getWindows()
        .find((candidate) => !candidate.isDestroyed());
      if (window) {
        if (window.isMinimized()) {
          window.restore();
        }
        window.show();
        window.focus();
        return;
      }

      try {
        await dependencies.openStartupWindow();
      } catch (error) {
        dependencies.onOpenStartupWindowFailed?.(error);
      }
    }
  };
}
