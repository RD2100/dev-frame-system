import { BrowserWindow, type IpcMainInvokeEvent } from "electron";

export function resolveOwnerWindowFromEvent(
  event: IpcMainInvokeEvent
): BrowserWindow | null {
  return BrowserWindow.fromWebContents(event.sender);
}
