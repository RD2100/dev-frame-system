import assert from "node:assert/strict";
import test from "node:test";
import { createDesktopNotificationActivation } from "./desktopNotificationActivation.ts";

test("desktop notification activation focuses an existing window", async () => {
  const calls: string[] = [];
  const activation = createDesktopNotificationActivation({
    focusApp() {
      calls.push("app.focus");
    },
    getWindows() {
      return [
        {
          focus() {
            calls.push("window.focus");
          },
          isDestroyed: () => false,
          isMinimized: () => false,
          restore() {
            calls.push("window.restore");
          },
          show() {
            calls.push("window.show");
          }
        }
      ];
    },
    async openStartupWindow() {
      calls.push("openStartupWindow");
    }
  });

  await activation.activate();

  assert.deepEqual(calls, ["app.focus", "window.show", "window.focus"]);
});

test("desktop notification activation restores minimized windows", async () => {
  const calls: string[] = [];
  const activation = createDesktopNotificationActivation({
    focusApp() {
      calls.push("app.focus");
    },
    getWindows() {
      return [
        {
          focus() {
            calls.push("window.focus");
          },
          isDestroyed: () => false,
          isMinimized: () => true,
          restore() {
            calls.push("window.restore");
          },
          show() {
            calls.push("window.show");
          }
        }
      ];
    },
    async openStartupWindow() {
      calls.push("openStartupWindow");
    }
  });

  await activation.activate();

  assert.deepEqual(calls, [
    "app.focus",
    "window.restore",
    "window.show",
    "window.focus"
  ]);
});

test("desktop notification activation opens startup window when no window exists", async () => {
  const calls: string[] = [];
  const activation = createDesktopNotificationActivation({
    focusApp() {
      calls.push("app.focus");
    },
    getWindows() {
      return [];
    },
    async openStartupWindow() {
      calls.push("openStartupWindow");
    }
  });

  await activation.activate();

  assert.deepEqual(calls, ["app.focus", "openStartupWindow"]);
});
