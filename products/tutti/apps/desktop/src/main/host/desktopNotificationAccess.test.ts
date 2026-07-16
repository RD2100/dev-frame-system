import assert from "node:assert/strict";
import test from "node:test";
import { createDesktopNotificationAccess } from "./desktopNotificationAccess.ts";

test("desktop notification access reports unsupported notifications without showing", () => {
  const shown: unknown[] = [];
  const access = createDesktopNotificationAccess({
    isSupported: () => false,
    createNotification(options) {
      return {
        on() {
          return this;
        },
        show() {
          shown.push(options);
        }
      };
    }
  });

  const result = access.show({
    body: "Check the app",
    title: "Run failed"
  });

  assert.deepEqual(result, {
    reason: "unsupported",
    shown: false
  });
  assert.deepEqual(shown, []);
});

test("desktop notification access shows supported notifications", () => {
  const shown: unknown[] = [];
  const failed: string[] = [];
  const access = createDesktopNotificationAccess({
    isSupported: () => true,
    createNotification(options) {
      return {
        on(event, listener) {
          if (event === "failed") {
            listener({}, "denied");
          }
          return this;
        },
        show() {
          shown.push(options);
        }
      };
    },
    onFailed(error) {
      failed.push(error);
    }
  });

  const result = access.show({
    body: "Check the app",
    title: "Run failed"
  });

  assert.deepEqual(result, { shown: true });
  assert.deepEqual(shown, [
    {
      body: "Check the app",
      title: "Run failed"
    }
  ]);
  assert.deepEqual(failed, ["denied"]);
});

test("desktop notification access invokes per-notification click callbacks", () => {
  const created: unknown[] = [];
  let activated = 0;
  let navigated = 0;
  const access = createDesktopNotificationAccess({
    isSupported: () => true,
    createNotification(options) {
      created.push(options);
      return {
        on(event, listener) {
          if (event === "click") {
            (listener as (event: unknown) => void)({});
          }
          return this;
        },
        show() {}
      };
    },
    onClick() {
      activated += 1;
    }
  });

  const result = access.show({
    body: "Approve the command",
    title: "Build feature needs your decision",
    onClick() {
      navigated += 1;
    }
  });

  assert.deepEqual(result, { shown: true });
  assert.equal(activated, 1);
  assert.equal(navigated, 1);
  assert.deepEqual(created, [
    {
      body: "Approve the command",
      title: "Build feature needs your decision"
    }
  ]);
});

test("desktop notification access invokes click callback", () => {
  let clicked = 0;
  const access = createDesktopNotificationAccess({
    isSupported: () => true,
    createNotification() {
      return {
        on(event, listener) {
          if (event === "click") {
            (listener as (event: unknown) => void)({});
          }
          return this;
        },
        show() {}
      };
    },
    onClick() {
      clicked += 1;
    }
  });

  const result = access.show({
    body: "Check the app",
    title: "Run failed"
  });

  assert.deepEqual(result, { shown: true });
  assert.equal(clicked, 1);
});
