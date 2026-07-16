import { BrowserWindow } from "electron";
import type { DesktopLogger } from "../logging.ts";

const perfMonitorDevToolsPath = "/__react-render-tracker__/standalone";

export interface OpenPerfMonitorDevToolsWindowOptions {
  logger?: DesktopLogger;
  ownerWindow?: BrowserWindow | null;
  rendererUrl: string;
  title: string;
}

let perfMonitorDevToolsWindow: BrowserWindow | null = null;

export function openPerfMonitorDevToolsWindow({
  logger,
  ownerWindow,
  rendererUrl,
  title
}: OpenPerfMonitorDevToolsWindowOptions): BrowserWindow {
  if (perfMonitorDevToolsWindow && !perfMonitorDevToolsWindow.isDestroyed()) {
    perfMonitorDevToolsWindow.show();
    perfMonitorDevToolsWindow.focus();
    return perfMonitorDevToolsWindow;
  }

  const devToolsUrl = new URL(perfMonitorDevToolsPath, rendererUrl).toString();
  const devToolsWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    show: false,
    title,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      ...(ownerWindow && !ownerWindow.isDestroyed()
        ? { session: ownerWindow.webContents.session }
        : {})
    }
  });

  perfMonitorDevToolsWindow = devToolsWindow;
  devToolsWindow.once("closed", () => {
    if (perfMonitorDevToolsWindow === devToolsWindow) {
      perfMonitorDevToolsWindow = null;
    }
  });
  devToolsWindow.once("ready-to-show", () => {
    devToolsWindow.show();
  });
  void devToolsWindow.loadURL(devToolsUrl).catch((error: unknown) => {
    logger?.warn("failed to load Perf Monitor DevTools", {
      error: error instanceof Error ? error.message : String(error),
      url: devToolsUrl
    });
  });

  return devToolsWindow;
}
