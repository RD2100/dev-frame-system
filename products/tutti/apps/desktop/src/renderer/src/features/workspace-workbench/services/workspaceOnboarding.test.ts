import assert from "node:assert/strict";
import test from "node:test";
import {
  workbenchSnapshotSchemaVersion,
  type WorkbenchSnapshot
} from "@tutti-os/workbench-snapshot";
import {
  hasWorkspaceOnboardingAutoOpened,
  writeWorkspaceOnboardingAutoOpenedToSnapshot
} from "./workspaceOnboarding.ts";

test("workspace onboarding reads missing or invalid metadata as not auto-opened", () => {
  assert.equal(hasWorkspaceOnboardingAutoOpened(null), false);
  assert.equal(
    hasWorkspaceOnboardingAutoOpened({
      ...createSnapshot(),
      metadata: {
        workspaceOnboarding: {
          autoOpened: "yes",
          schemaVersion: 1
        }
      }
    }),
    false
  );
});

test("workspace onboarding auto-open state round-trips through snapshot metadata", () => {
  const snapshot = writeWorkspaceOnboardingAutoOpenedToSnapshot(
    {
      ...createSnapshot(),
      metadata: {
        anotherFeature: {
          enabled: true
        }
      }
    },
    "2026-06-18T00:00:00.000Z"
  );

  assert.equal(hasWorkspaceOnboardingAutoOpened(snapshot), true);
  assert.deepEqual(snapshot.metadata, {
    anotherFeature: {
      enabled: true
    },
    workspaceOnboarding: {
      autoOpened: true,
      autoOpenedAt: "2026-06-18T00:00:00.000Z",
      schemaVersion: 1
    }
  });
});

test("workspace onboarding state does not access localStorage", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() {
      throw new Error("localStorage should not be accessed");
    }
  });
  try {
    const snapshot =
      writeWorkspaceOnboardingAutoOpenedToSnapshot(createSnapshot());
    assert.equal(hasWorkspaceOnboardingAutoOpened(snapshot), true);
  } finally {
    if (original) {
      Object.defineProperty(globalThis, "localStorage", original);
    } else {
      Reflect.deleteProperty(globalThis, "localStorage");
    }
  }
});

function createSnapshot(): WorkbenchSnapshot {
  return {
    schemaVersion: workbenchSnapshotSchemaVersion,
    nodes: [],
    nodeStack: [],
    activeNodeId: null
  };
}
