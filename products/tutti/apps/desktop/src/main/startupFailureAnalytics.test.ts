import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import type { TrackEvent } from "@tutti-os/client-tuttid-ts";
import {
  createStartupFailureEvent,
  flushStartupFailureEvents,
  recordStartupFailureEvent
} from "./startupFailureAnalytics.ts";

test("startup failure analytics creates safe app startup failed params", () => {
  const event = createStartupFailureEvent({
    error: Object.assign(new Error("secret local path /Users/example/app"), {
      code: "ENOENT"
    }),
    name: "app.startup_failed",
    now: () => 1749124800000,
    process: "main"
  });

  assert.deepEqual(event, {
    client_ts: 1749124800000,
    name: "app.startup_failed",
    params: {
      error_message: "Daemon runtime information is unavailable.",
      error_type: "daemon_unavailable",
      process: "main"
    }
  });
});

test("startup failure analytics records and flushes queued events", async () => {
  const dir = await mkdtemp(join(tmpdir(), "tutti-startup-analytics-"));
  const queuePath = join(dir, "startup-failures.jsonl");
  const events: TrackEvent[][] = [];

  await recordStartupFailureEvent({
    error: new Error("connection refused"),
    name: "daemon.startup_failed",
    now: () => 1749124800123,
    queuePath
  });

  const queued = await readFile(queuePath, "utf8");
  assert.match(queued, /"name":"daemon.startup_failed"/);

  await flushStartupFailureEvents({
    tuttidClient: {
      async trackEvents(nextEvents) {
        events.push(nextEvents);
      }
    },
    queuePath
  });

  assert.deepEqual(events, [
    [
      {
        client_ts: 1749124800123,
        name: "daemon.startup_failed",
        params: {
          error_message: "Daemon connection failed.",
          error_type: "transport_connect_failed"
        }
      }
    ]
  ]);
  await assert.rejects(() => readFile(queuePath, "utf8"));
});
