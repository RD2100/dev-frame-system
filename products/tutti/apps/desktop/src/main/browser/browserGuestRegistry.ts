import type { BrowserWindow, WebContents } from "electron";
import type { BrowserNodeElectronLogger } from "@tutti-os/browser-node/electron-main";

const browserGuestIdsByWindow = new WeakMap<BrowserWindow, Set<number>>();
const windowsWithGuestRegistryCloseListener = new WeakSet<BrowserWindow>();

export function registerBrowserGuestWebContents(
  ownerWindow: BrowserWindow,
  guestContents: WebContents,
  logger?: BrowserNodeElectronLogger
): void {
  let guestIds = browserGuestIdsByWindow.get(ownerWindow);
  if (!guestIds) {
    guestIds = new Set<number>();
    browserGuestIdsByWindow.set(ownerWindow, guestIds);
  }

  guestIds.add(guestContents.id);
  logger?.debug?.("Browser Node registered guest webContents", {
    attachedGuestIds: [...guestIds],
    ownerWindowId: ownerWindow.id,
    webContentsId: guestContents.id
  });
  guestContents.once("destroyed", () => {
    guestIds.delete(guestContents.id);
    logger?.debug?.("Browser Node guest webContents destroyed", {
      attachedGuestIds: [...guestIds],
      ownerWindowId: ownerWindow.id,
      webContentsId: guestContents.id
    });
  });
  if (!windowsWithGuestRegistryCloseListener.has(ownerWindow)) {
    windowsWithGuestRegistryCloseListener.add(ownerWindow);
    ownerWindow.once("closed", () => {
      guestIds.clear();
    });
  }
}

export function isBrowserGuestWebContentsAttachedToWindow(
  ownerWindow: BrowserWindow,
  webContentsId: number
): boolean {
  return browserGuestIdsByWindow.get(ownerWindow)?.has(webContentsId) ?? false;
}

export function getBrowserGuestWebContentsIdsForWindow(
  ownerWindow: BrowserWindow
): number[] {
  return [...(browserGuestIdsByWindow.get(ownerWindow) ?? [])];
}
