import { ipcRenderer } from "electron";
import {
  desktopIpcChannels,
  type BrowserNodeEvent
} from "../../shared/contracts/ipc";
import { isDesktopDevelopmentRuntime } from "../../shared/runtimeEnvironment";
import type { DesktopBrowserApi } from "../types";
import { invokeDesktopApi } from "./invoke";

export function createBrowserDesktopApi(): DesktopBrowserApi {
  const api: DesktopBrowserApi = {
    activate(payload) {
      return invokeDesktopApi(desktopIpcChannels.browser.activate, payload);
    },
    capturePreview(payload) {
      return invokeDesktopApi(
        desktopIpcChannels.browser.capturePreview,
        payload
      );
    },
    close(payload) {
      return invokeDesktopApi(desktopIpcChannels.browser.close, payload);
    },
    goBack(payload) {
      return invokeDesktopApi(desktopIpcChannels.browser.goBack, payload);
    },
    goForward(payload) {
      return invokeDesktopApi(desktopIpcChannels.browser.goForward, payload);
    },
    navigate(payload) {
      return invokeDesktopApi(desktopIpcChannels.browser.navigate, payload);
    },
    ...(isBrowserDevToolsEnabled()
      ? {
          openDevTools(payload) {
            return invokeDesktopApi(
              desktopIpcChannels.browser.openDevTools,
              payload
            );
          },
          showDevToolsContextMenu(payload) {
            return invokeDesktopApi(
              desktopIpcChannels.browser.showDevToolsContextMenu,
              payload
            );
          }
        }
      : {}),
    openExternal(payload) {
      return invokeDesktopApi(desktopIpcChannels.browser.openExternal, payload);
    },
    onEvent(listener: (event: BrowserNodeEvent) => void): () => void {
      const handler = (
        _event: Electron.IpcRendererEvent,
        payload: BrowserNodeEvent
      ) => {
        listener(payload);
      };

      ipcRenderer.on(desktopIpcChannels.browser.event, handler);

      return () => {
        ipcRenderer.removeListener(desktopIpcChannels.browser.event, handler);
      };
    },
    prepareSession(payload) {
      return invokeDesktopApi(
        desktopIpcChannels.browser.prepareSession,
        payload
      );
    },
    registerGuest(payload) {
      return invokeDesktopApi(
        desktopIpcChannels.browser.registerGuest,
        payload
      );
    },
    reload(payload) {
      return invokeDesktopApi(desktopIpcChannels.browser.reload, payload);
    },
    unregisterGuest(payload) {
      return invokeDesktopApi(
        desktopIpcChannels.browser.unregisterGuest,
        payload
      );
    }
  };
  return api;
}

function isBrowserDevToolsEnabled(): boolean {
  return isDesktopDevelopmentRuntime({
    tuttiEnv: process.env.TUTTI_ENV,
    nodeEnv: process.env.NODE_ENV
  });
}
