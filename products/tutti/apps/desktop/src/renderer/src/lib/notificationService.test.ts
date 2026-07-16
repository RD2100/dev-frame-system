import assert from "node:assert/strict";
import test from "node:test";
import type { NotificationMessage } from "@tutti-os/ui-notifications";
import {
  createCompositeNotificationService,
  createDefaultBackgroundNotificationPolicy,
  createDocumentNotificationVisibilityState,
  createHostBackgroundNotificationPresenter
} from "./compositeNotificationService.ts";

test("composite notification service keeps background notifications quiet while foreground", () => {
  const foregroundMessages: NotificationMessage[] = [];
  const backgroundMessages: NotificationMessage[] = [];
  const service = createCompositeNotificationService({
    background: {
      show(message) {
        backgroundMessages.push(message);
      }
    },
    foreground: {
      show(message) {
        foregroundMessages.push(message);
      }
    },
    policy: createDefaultBackgroundNotificationPolicy(),
    visibility: {
      isForeground: () => true
    }
  });

  service.error({ title: "Save failed", description: "Disk is full" });

  assert.deepEqual(foregroundMessages, [
    {
      description: "Disk is full",
      level: "error",
      title: "Save failed"
    }
  ]);
  assert.deepEqual(backgroundMessages, []);
});

test("composite notification service mirrors all notification levels when not foreground", () => {
  const foregroundMessages: NotificationMessage[] = [];
  const backgroundMessages: NotificationMessage[] = [];
  const service = createCompositeNotificationService({
    background: {
      show(message) {
        backgroundMessages.push(message);
      }
    },
    foreground: {
      show(message) {
        foregroundMessages.push(message);
      }
    },
    policy: createDefaultBackgroundNotificationPolicy(),
    visibility: {
      isForeground: () => false
    }
  });

  service.error({ title: "Run failed" });
  service.success({ title: "Saved" });
  service.info({ title: "Started" });
  service.warning({ title: "Check settings" });

  assert.deepEqual(
    foregroundMessages.map((message) => message.title),
    ["Run failed", "Saved", "Started", "Check settings"]
  );
  assert.deepEqual(backgroundMessages, [
    {
      level: "error",
      title: "Run failed"
    },
    {
      level: "success",
      title: "Saved"
    },
    {
      level: "info",
      title: "Started"
    },
    {
      level: "warning",
      title: "Check settings"
    }
  ]);
});

test("host background notification presenter forwards title and description", async () => {
  const calls: unknown[] = [];
  const presenter = createHostBackgroundNotificationPresenter({
    show(input) {
      calls.push(input);
      return Promise.resolve({ shown: true });
    }
  });

  await presenter.show({
    description: "Open Tutti OS for details",
    level: "warning",
    title: "Action required"
  });

  assert.deepEqual(calls, [
    {
      body: "Open Tutti OS for details",
      level: "warning",
      title: "Action required"
    }
  ]);
});

test("composite notification service honors the background notification policy", () => {
  const foregroundMessages: NotificationMessage[] = [];
  const backgroundMessages: NotificationMessage[] = [];
  const service = createCompositeNotificationService({
    background: {
      show(message) {
        backgroundMessages.push(message);
      }
    },
    foreground: {
      show(message) {
        foregroundMessages.push(message);
      }
    },
    policy: {
      shouldNotifyInBackground(message) {
        return message.level === "error";
      }
    },
    visibility: {
      isForeground: () => false
    }
  });

  service.info({ title: "Started" });
  service.error({ title: "Run failed" });

  assert.deepEqual(
    foregroundMessages.map((message) => message.title),
    ["Started", "Run failed"]
  );
  assert.deepEqual(backgroundMessages, [
    {
      level: "error",
      title: "Run failed"
    }
  ]);
});

test("composite notification service isolates background presenter failures", () => {
  const foregroundMessages: NotificationMessage[] = [];
  const service = createCompositeNotificationService({
    background: {
      show() {
        throw new Error("host notification unavailable");
      }
    },
    foreground: {
      show(message) {
        foregroundMessages.push(message);
      }
    },
    policy: createDefaultBackgroundNotificationPolicy(),
    visibility: {
      isForeground: () => false
    }
  });

  assert.doesNotThrow(() => {
    service.error({ title: "Run failed" });
  });
  assert.deepEqual(foregroundMessages, [
    {
      level: "error",
      title: "Run failed"
    }
  ]);
});

test("document notification visibility requires visible and focused document", () => {
  assert.equal(
    createDocumentNotificationVisibilityState({
      hasFocus: () => true,
      visibilityState: () => "visible"
    }).isForeground(),
    true
  );
  assert.equal(
    createDocumentNotificationVisibilityState({
      hasFocus: () => false,
      visibilityState: () => "visible"
    }).isForeground(),
    false
  );
  assert.equal(
    createDocumentNotificationVisibilityState({
      hasFocus: () => true,
      visibilityState: () => "hidden"
    }).isForeground(),
    false
  );
});
