import assert from "node:assert/strict";
import test from "node:test";
import { createTerminalAttachmentController } from "./attachmentController.ts";

function createDeferred<T>() {
  let reject!: (error: unknown) => void;
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, reject, resolve };
}

test("attachment controller detaches only after an in-flight attach completes", async () => {
  const attachDeferred = createDeferred<void>();
  const events: string[] = [];
  const controller = createTerminalAttachmentController({
    clientId: "client-1",
    sessionId: "term-1",
    transport: {
      attach: async () => {
        events.push("attach");
        return attachDeferred.promise;
      },
      detach: async () => {
        events.push("detach");
      }
    }
  });

  const attachPromise = controller.attach(7);
  const detachPromise = controller.detach();

  await Promise.resolve();
  assert.deepEqual(events, ["attach"]);

  attachDeferred.resolve();
  await attachPromise;
  await detachPromise;

  assert.deepEqual(events, ["attach", "detach"]);
});

test("attachment controller does not detach after a failed attach", async () => {
  const controller = createTerminalAttachmentController({
    clientId: "client-1",
    sessionId: "term-1",
    transport: {
      attach: async () => {
        throw new Error("attach failed");
      },
      detach: async () => {
        throw new Error("detach should not run");
      }
    }
  });

  await assert.rejects(() => controller.attach(), /attach failed/);
  await controller.detach();
});
