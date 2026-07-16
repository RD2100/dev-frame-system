import assert from "node:assert/strict";
import test from "node:test";
import { closeTerminalSession } from "./closeFlow.ts";
import type { TerminalNodeFeature } from "./feature.ts";

test("closeTerminalSession terminates immediately when guard allows close", async () => {
  const events: string[] = [];
  const feature = createCloseFeature({
    events,
    reason: "running",
    requiresConfirmation: false,
    terminate: async () => {
      events.push("terminate");
    }
  });

  const result = await closeTerminalSession({
    feature,
    sessionId: "term-1"
  });

  assert.equal(result, "closed");
  assert.deepEqual(events, [
    "diagnostic:close-requested",
    "terminate",
    "diagnostic:close-confirmed"
  ]);
});

test("closeTerminalSession keeps session open when confirmation is rejected", async () => {
  const events: string[] = [];
  const feature = createCloseFeature({
    events,
    requiresConfirmation: true,
    terminate: async () => {
      events.push("terminate");
    }
  });

  const result = await closeTerminalSession({
    confirm: () => false,
    feature,
    sessionId: "term-1"
  });

  assert.equal(result, "kept-open");
  assert.deepEqual(events, ["diagnostic:close-requested"]);
});

test("closeTerminalSession closes ended sessions without host calls", async () => {
  const events: string[] = [];
  let terminateCalls = 0;
  const feature = createCloseFeature({
    events,
    requiresConfirmation: false,
    terminate: async () => {
      terminateCalls += 1;
    }
  });

  const result = await closeTerminalSession({
    feature,
    sessionId: "term-1",
    status: "failed"
  });

  assert.equal(result, "closed");
  assert.equal(terminateCalls, 0);
  assert.deepEqual(events, []);
});

test("closeTerminalSession still terminates idle sessions when guard reports not-running", async () => {
  const events: string[] = [];
  let terminateCalls = 0;
  const feature = createCloseFeature({
    events,
    requiresConfirmation: false,
    reason: "not-running",
    status: "running",
    terminate: async () => {
      terminateCalls += 1;
    }
  });

  const result = await closeTerminalSession({
    feature,
    sessionId: "term-1"
  });

  assert.equal(result, "closed");
  assert.equal(terminateCalls, 1);
  assert.deepEqual(events, [
    "diagnostic:close-requested",
    "diagnostic:close-confirmed"
  ]);
});

test("closeTerminalSession treats ended not-running guards as already closed", async () => {
  const events: string[] = [];
  let terminateCalls = 0;
  const feature = createCloseFeature({
    events,
    requiresConfirmation: false,
    reason: "not-running",
    status: "failed",
    terminate: async () => {
      terminateCalls += 1;
    }
  });

  const result = await closeTerminalSession({
    feature,
    sessionId: "term-1"
  });

  assert.equal(result, "closed");
  assert.equal(terminateCalls, 0);
  assert.deepEqual(events, [
    "diagnostic:close-requested",
    "diagnostic:close-confirmed"
  ]);
});

function createCloseFeature(input: {
  events: string[];
  reason?: "running" | "not-running";
  requiresConfirmation: boolean;
  status?: "running" | "failed";
  terminate(): Promise<void>;
}): Pick<TerminalNodeFeature, "closeGuard" | "diagnostics" | "launchService"> {
  return {
    closeGuard: {
      async check() {
        return {
          reason:
            input.reason ??
            (input.requiresConfirmation ? "running" : "not-running"),
          requiresConfirmation: input.requiresConfirmation,
          status: input.status ?? "running"
        };
      }
    },
    diagnostics: {
      log(event) {
        input.events.push(`diagnostic:${event}`);
      }
    },
    launchService: {
      async create() {
        throw new Error("not used");
      },
      terminate: () => input.terminate()
    }
  };
}
