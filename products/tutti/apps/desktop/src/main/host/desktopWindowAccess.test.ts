import assert from "node:assert/strict";
import test from "node:test";
import { createDesktopWindowAccess } from "./desktopWindowAccess.ts";
import type { WorkspaceLaunchOwnerWindow } from "./workspaceLaunch.ts";

test("desktop window access approves close by closing the current owner window", async () => {
  const events: string[] = [];
  const ownerWindow: WorkspaceLaunchOwnerWindow = {
    close() {
      events.push("owner:closed");
    }
  };

  await createDesktopWindowAccess().approveClose(ownerWindow);

  assert.deepEqual(events, ["owner:closed"]);
});

test("desktop window access prefers destroy after close is approved", async () => {
  const events: string[] = [];
  const ownerWindow: WorkspaceLaunchOwnerWindow = {
    close() {
      events.push("owner:closed");
    },
    destroy() {
      events.push("owner:destroyed");
    }
  };

  await createDesktopWindowAccess().approveClose(ownerWindow);

  assert.deepEqual(events, ["owner:destroyed"]);
});
