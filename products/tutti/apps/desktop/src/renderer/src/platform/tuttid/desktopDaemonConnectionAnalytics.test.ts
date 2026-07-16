import assert from "node:assert/strict";
import test from "node:test";
import type { ReporterEventInput } from "../../features/analytics/services/reporterService.interface.ts";
import {
  startDesktopDaemonConnectionAnalytics,
  type TuttidEventStreamConnectionState
} from "./desktopDaemonConnectionAnalytics.ts";

test("daemon connection analytics reports a disconnected cycle after reconnect", async () => {
  const listeners = new Set<
    (state: TuttidEventStreamConnectionState) => void
  >();
  const calls: ReporterEventInput[][] = [];
  let currentTime = 1000;
  const lease = startDesktopDaemonConnectionAnalytics({
    eventStreamClient: {
      subscribeConnectionState(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      }
    },
    now: () => currentTime,
    reporterService: {
      async trackEvents(events) {
        calls.push(events);
      }
    }
  });

  emit(listeners, "connecting");
  emit(listeners, "connected");
  currentTime = 1500;
  emit(listeners, "disconnected");
  currentTime = 2300;
  emit(listeners, "connecting");
  emit(listeners, "connected");
  await flushAsyncWork();

  assert.deepEqual(calls, [
    [
      {
        clientTS: 1500,
        name: "daemon.disconnected",
        params: {
          reason: "unknown"
        }
      },
      {
        clientTS: 2300,
        name: "daemon.reconnected",
        params: {
          downtime_ms: 800
        }
      }
    ]
  ]);

  lease.release();
  assert.equal(listeners.size, 0);
});

test("daemon connection analytics ignores pre-connect disconnected states", async () => {
  const listeners = new Set<
    (state: TuttidEventStreamConnectionState) => void
  >();
  const calls: ReporterEventInput[][] = [];
  startDesktopDaemonConnectionAnalytics({
    eventStreamClient: {
      subscribeConnectionState(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      }
    },
    reporterService: {
      async trackEvents(events) {
        calls.push(events);
      }
    }
  });

  emit(listeners, "disconnected");
  emit(listeners, "connecting");
  emit(listeners, "connected");
  await flushAsyncWork();

  assert.deepEqual(calls, []);
});

function emit(
  listeners: Set<(state: TuttidEventStreamConnectionState) => void>,
  state: TuttidEventStreamConnectionState
): void {
  for (const listener of listeners) {
    listener(state);
  }
}

async function flushAsyncWork(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}
