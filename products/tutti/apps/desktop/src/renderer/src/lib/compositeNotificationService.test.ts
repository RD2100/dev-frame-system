import assert from "node:assert/strict";
import test from "node:test";
import type { NotificationMessage } from "@tutti-os/ui-notifications";
import {
  createCompositeNotificationService,
  createDefaultBackgroundNotificationPolicy,
  createHostBackgroundNotificationPresenter,
  type CompositeNotificationMessage
} from "./compositeNotificationService.ts";

function createHarness(input: { foreground: boolean }) {
  const backgroundMessages: NotificationMessage[] = [];
  const foregroundMessages: NotificationMessage[] = [];
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
      isForeground() {
        return input.foreground;
      }
    }
  });
  return { backgroundMessages, foregroundMessages, service };
}

test("composite notification service shows default messages on both faces when unfocused", () => {
  const harness = createHarness({ foreground: false });

  harness.service.notify({
    description: "Summary",
    level: "info",
    title: "Conversation update"
  });

  assert.equal(harness.foregroundMessages.length, 1);
  assert.equal(harness.backgroundMessages.length, 1);
});

test("composite notification service keeps default messages foreground-only when focused", () => {
  const harness = createHarness({ foreground: true });

  harness.service.notify({
    description: "Summary",
    level: "info",
    title: "Conversation update"
  });

  assert.equal(harness.foregroundMessages.length, 1);
  assert.equal(harness.backgroundMessages.length, 0);
});

test("composite notification service sends background-only waiting decisions to the OS face when unfocused", () => {
  const harness = createHarness({ foreground: false });
  const message: CompositeNotificationMessage = {
    description: "Command: rm -rf dist",
    level: "warning",
    presentation: "background-only",
    title: "Build feature needs your decision"
  };

  harness.service.notify(message);

  assert.equal(harness.foregroundMessages.length, 0);
  assert.equal(harness.backgroundMessages.length, 1);
  assert.equal(
    harness.backgroundMessages[0]?.title,
    "Build feature needs your decision"
  );
});

test("composite notification service suppresses background-only messages when focused", () => {
  const harness = createHarness({ foreground: true });
  const message: CompositeNotificationMessage = {
    description: "Command: rm -rf dist",
    level: "warning",
    presentation: "background-only",
    title: "Build feature needs your decision"
  };

  harness.service.notify(message);

  assert.equal(harness.foregroundMessages.length, 0);
  assert.equal(harness.backgroundMessages.length, 0);
});

test("host background notification presenter forwards navigation to the host api", async () => {
  const shown: unknown[] = [];
  const presenter = createHostBackgroundNotificationPresenter({
    show(input) {
      shown.push(input);
    }
  });
  const message: CompositeNotificationMessage = {
    description: "Command: rm -rf dist",
    level: "warning",
    navigation: {
      agentSessionId: "session-1",
      provider: "codex",
      workspaceId: "workspace-1"
    },
    presentation: "background-only",
    title: "Build feature needs your decision"
  };

  await presenter.show(message);

  assert.deepEqual(shown, [
    {
      body: "Command: rm -rf dist",
      level: "warning",
      navigation: {
        agentSessionId: "session-1",
        provider: "codex",
        workspaceId: "workspace-1"
      },
      title: "Build feature needs your decision"
    }
  ]);
});

test("host background notification presenter omits navigation when absent", async () => {
  const shown: Array<{ navigation?: unknown }> = [];
  const presenter = createHostBackgroundNotificationPresenter({
    show(input) {
      shown.push(input);
    }
  });

  await presenter.show({
    description: "Summary",
    level: "info",
    title: "Conversation update"
  });

  assert.equal(shown.length, 1);
  assert.equal(shown[0]?.navigation, undefined);
});

test("composite notification service keeps foreground-only messages off the OS face", () => {
  const harness = createHarness({ foreground: false });
  const message: CompositeNotificationMessage = {
    description: "Summary",
    level: "error",
    presentation: "foreground-only",
    title: "Conversation Build feature Failed"
  };

  harness.service.notify(message);

  assert.equal(harness.foregroundMessages.length, 1);
  assert.equal(harness.backgroundMessages.length, 0);
});
