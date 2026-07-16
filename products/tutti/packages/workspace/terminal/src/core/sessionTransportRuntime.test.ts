import assert from "node:assert/strict";
import test from "node:test";
import type {
  TerminalDataEvent,
  TerminalStateEvent,
  TerminalSnapshot,
  TerminalTransport
} from "../contracts/index.ts";
import { acquireTerminalSessionTransportRuntime } from "./sessionTransportRuntime.ts";

test("session transport runtime shares in-flight snapshot work across remounts", async () => {
  let snapshotCalls = 0;
  const snapshotDeferred = createDeferred<TerminalSnapshot>();
  const transport = createTransport({
    snapshot: async () => {
      snapshotCalls += 1;
      return snapshotDeferred.promise;
    }
  });

  const first = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 0,
    sessionId: "term-runtime-1",
    transport
  });
  const second = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 0,
    sessionId: "term-runtime-1",
    transport
  });

  const firstSnapshot = first.snapshot();
  const secondSnapshot = second.snapshot();
  snapshotDeferred.resolve({
    data: "hello",
    toSeq: 7
  });

  assert.equal(snapshotCalls, 1);
  assert.deepEqual(await firstSnapshot, { data: "hello", toSeq: 7 });
  assert.deepEqual(await secondSnapshot, { data: "hello", toSeq: 7 });

  first.release();
  second.release();
  await waitForTimerTick();
});

test("session transport runtime buffers transport data between remounts", async () => {
  const dataListeners = new Set<(event: TerminalDataEvent) => void>();
  const transport = createTransport({
    onData(listener) {
      dataListeners.add(listener);
      return () => dataListeners.delete(listener);
    }
  });

  const first = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 10,
    sessionId: "term-runtime-2",
    transport
  });
  const firstEvents: string[] = [];
  const unsubscribeFirst = first.onData((event) => {
    firstEvents.push(event.data);
  });

  dataListeners.forEach((listener) =>
    listener({ data: "before-release", sessionId: "term-runtime-2" })
  );
  unsubscribeFirst();
  first.release();

  dataListeners.forEach((listener) =>
    listener({ data: "buffered", sessionId: "term-runtime-2" })
  );

  const second = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 10,
    sessionId: "term-runtime-2",
    transport
  });
  const secondEvents: string[] = [];
  const unsubscribeSecond = second.onData((event) => {
    secondEvents.push(event.data);
  });

  assert.deepEqual(firstEvents, ["before-release"]);
  assert.deepEqual(secondEvents, ["buffered"]);

  unsubscribeSecond();
  second.release();
  await waitForTimerTick(15);
});

test("session transport runtime delays detach long enough for strict-mode remount", async () => {
  const events: string[] = [];
  const transport = createTransport({
    async attach() {
      events.push("attach");
    },
    async detach() {
      events.push("detach");
    }
  });

  const first = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 20,
    sessionId: "term-runtime-3",
    transport
  });
  await first.attach(4);
  first.release();

  const second = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 20,
    sessionId: "term-runtime-3",
    transport
  });
  await second.attach(4);
  await waitForTimerTick(30);

  assert.deepEqual(events, ["attach"]);

  second.release();
  await waitForTimerTick(30);

  assert.deepEqual(events, ["attach", "detach"]);
});

test("session transport runtime reuses cached snapshot across remount churn while attached", async () => {
  let snapshotCalls = 0;
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
      snapshotCalls += 1;
      return {
        data: "cached-output",
        toSeq: 9
      };
    }
  });

  const first = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 80,
    sessionId: "term-runtime-4",
    transport
  });

  assert.deepEqual(await first.snapshot(), {
    data: "cached-output",
    toSeq: 9
  });
  await first.attach(9);
  requireStateListener(stateListener)({
    error: null,
    sessionId: "term-runtime-4",
    status: "running"
  });
  first.release();

  await waitForTimerTick(30);

  const second = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 80,
    sessionId: "term-runtime-4",
    transport
  });

  assert.deepEqual(await second.snapshot(), {
    data: "cached-output",
    toSeq: 9
  });
  assert.equal(snapshotCalls, 1);

  second.release();
  await waitForTimerTick(100);
});

test("session transport runtime invalidates cached snapshot when a replay gap is reported", async () => {
  let snapshotCalls = 0;
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
      snapshotCalls += 1;
      return {
        data: `snapshot-${snapshotCalls}`,
        toSeq: snapshotCalls
      };
    }
  });

  const runtime = acquireTerminalSessionTransportRuntime({
    detachGraceMs: 0,
    sessionId: "term-runtime-5",
    transport
  });

  await runtime.snapshot();
  requireStateListener(stateListener)({
    gapEndSeq: 8,
    gapStartSeq: 4,
    sessionId: "term-runtime-5",
    status: "running"
  });
  await runtime.snapshot();

  assert.equal(snapshotCalls, 2);

  runtime.release();
  await waitForTimerTick();
});

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
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
      return (await overrides.snapshot?.(input)) ?? { data: "" };
    },
    async write() {
      return undefined;
    }
  };
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
