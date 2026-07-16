import assert from "node:assert/strict";
import test from "node:test";
import type {
  TerminalDataEvent,
  TerminalSnapshot,
  TerminalStateEvent,
  TerminalTransport
} from "../contracts/index.ts";
import type { TerminalNodeFeature } from "./feature.ts";
import {
  createTerminalNodeFeature,
  defaultTerminalNodeLimits
} from "./feature.ts";
import { acquireTerminalSessionController } from "./sessionController.ts";

test("session controller owns snapshot and attach across remount churn", async () => {
  let attachCalls = 0;
  let snapshotCalls = 0;
  const dataListeners = new Set<(event: TerminalDataEvent) => void>();
  const transport = createTransport({
    async attach() {
      attachCalls += 1;
    },
    onData(listener) {
      dataListeners.add(listener);
      return () => dataListeners.delete(listener);
    },
    async snapshot() {
      snapshotCalls += 1;
      return {
        data: "hello",
        toSeq: 3
      };
    }
  });
  const feature = createFeature(transport);

  const first = acquireTerminalSessionController({
    feature,
    nodeId: "node-1",
    retainMs: 60,
    sessionId: "session-1"
  });
  first.retain();
  await waitFor(() => first.getState().inputReady);
  dataListeners.forEach((listener) =>
    listener({ data: " world", sessionId: "session-1" })
  );
  await waitFor(() => first.getState().rawOutput === "hello world");
  first.release();

  await waitForTimerTick(20);

  const second = acquireTerminalSessionController({
    feature,
    nodeId: "node-1",
    retainMs: 60,
    sessionId: "session-1"
  });
  second.retain();

  assert.equal(snapshotCalls, 1);
  assert.equal(attachCalls, 1);
  assert.equal(second.getState().rawOutput, "hello world");
  assert.equal(second.getState().inputReady, true);

  second.release();
  await waitForTimerTick(320);
});

test("session controller projects replay gaps into surface error state", async () => {
  let stateListener: ((event: TerminalStateEvent) => void) | null = null;
  const transport = createTransport({
    onState(listener) {
      stateListener = listener;
      return () => {
        if (stateListener === listener) {
          stateListener = null;
        }
      };
    },
    async snapshot() {
      return {
        data: "gap-test",
        toSeq: 7
      };
    }
  });
  const feature = createFeature(transport);
  const controller = acquireTerminalSessionController({
    feature,
    nodeId: "node-2",
    retainMs: 0,
    sessionId: "session-2"
  });
  controller.retain();

  await waitFor(() => controller.getState().inputReady);
  requireStateListener(stateListener)({
    gapEndSeq: 9,
    gapStartSeq: 8,
    sessionId: "session-2",
    status: "running"
  });

  assert.equal(
    controller.getState().surfaceError,
    "terminalNode.recovery.replayGap"
  );

  controller.release();
  await waitForTimerTick(260);
});

test("session controller reattaches and flushes queued input after detach", async () => {
  let attachCalls = 0;
  let stateListener: ((event: TerminalStateEvent) => void) | null = null;
  const writes: string[] = [];
  const transport = createTransport({
    async attach() {
      attachCalls += 1;
    },
    onState(listener) {
      stateListener = listener;
      return () => {
        if (stateListener === listener) {
          stateListener = null;
        }
      };
    },
    async snapshot() {
      return {
        data: "ready",
        toSeq: 2
      };
    },
    async write(input) {
      writes.push(input.data);
    }
  });
  const feature = createFeature(transport);
  const controller = acquireTerminalSessionController({
    feature,
    nodeId: "node-3",
    retainMs: 0,
    sessionId: "session-3"
  });
  controller.retain();

  await waitFor(() => controller.getState().inputReady);
  requireStateListener(stateListener)({
    error: null,
    sessionId: "session-3",
    status: "detached"
  });
  controller.write("pwd\n");

  await waitFor(() => attachCalls === 2);
  await waitFor(() => controller.getState().inputReady);
  await waitFor(() => writes.length === 1);
  assert.deepEqual(writes, ["pwd\n"]);

  controller.release();
  await waitForTimerTick(260);
});

test("session controller cancels pending teardown when retained again", async () => {
  let attachCalls = 0;
  let detachCalls = 0;
  const transport = createTransport({
    async attach() {
      attachCalls += 1;
    },
    async detach() {
      detachCalls += 1;
    },
    async snapshot() {
      return {
        data: "stable",
        toSeq: 1
      };
    }
  });
  const feature = createFeature(transport);
  const controller = acquireTerminalSessionController({
    feature,
    nodeId: "node-4",
    retainMs: 40,
    sessionId: "session-4"
  });

  controller.retain();
  await waitFor(() => controller.getState().inputReady);
  controller.release();

  await waitForTimerTick(10);
  controller.retain();
  await waitForTimerTick(80);

  assert.equal(attachCalls, 1);
  assert.equal(detachCalls, 0);

  controller.release();
  await waitForTimerTick(320);
  assert.equal(detachCalls, 1);
});

function createFeature(transport: TerminalTransport): TerminalNodeFeature {
  return createTerminalNodeFeature({
    closeGuard: {
      async check() {
        return {
          reason: "unknown",
          requiresConfirmation: false,
          status: "running"
        };
      }
    },
    diagnostics: {
      log() {
        return undefined;
      }
    },
    i18n: {
      t(key: string) {
        return key;
      }
    } as TerminalNodeFeature["i18n"],
    launchService: {
      async create() {
        throw new Error("not implemented");
      },
      async terminate() {
        return undefined;
      }
    },
    limits: defaultTerminalNodeLimits,
    transport
  });
}

function createTransport(
  overrides: Partial<TerminalTransport> = {}
): TerminalTransport {
  return {
    async attach(input) {
      return overrides.attach?.(input);
    },
    async detach(input) {
      return overrides.detach?.(input);
    },
    onData(listener) {
      return overrides.onData?.(listener) ?? (() => undefined);
    },
    onExit(listener) {
      return overrides.onExit?.(listener) ?? (() => undefined);
    },
    onMetadata(listener) {
      return overrides.onMetadata?.(listener) ?? (() => undefined);
    },
    onState(listener) {
      return overrides.onState?.(listener) ?? (() => undefined);
    },
    async resize() {
      return undefined;
    },
    async snapshot(input) {
      return (await overrides.snapshot?.(input)) ?? emptySnapshot;
    },
    async write(input) {
      return overrides.write?.(input);
    }
  };
}

const emptySnapshot: TerminalSnapshot = { data: "" };

async function waitFor(condition: () => boolean, timeoutMs = 200) {
  const startedAt = Date.now();
  while (!condition()) {
    if (Date.now() - startedAt > timeoutMs) {
      assert.fail("timed out waiting for condition");
    }
    await waitForTimerTick(5);
  }
}

function waitForTimerTick(delay = 0) {
  return new Promise<void>((resolve) => {
    setTimeout(resolve, delay);
  });
}

function requireStateListener(
  listener: ((event: TerminalStateEvent) => void) | null
) {
  if (listener === null) {
    assert.fail("expected terminal state listener to be registered");
  }
  return listener;
}
