import assert from "node:assert/strict";
import test from "node:test";
import {
  createBufferedTerminalInputQueue,
  writeQueuedTerminalInput
} from "./inputQueue.ts";

test("buffered terminal input queue preserves binary and utf8 ordering", async () => {
  const queue = createBufferedTerminalInputQueue();
  const writes: Array<{ data: string; encoding?: string }> = [];

  queue.enqueue("ls\n");
  queue.enqueue("\u0003", "binary");

  await writeQueuedTerminalInput({
    queue,
    sessionId: "term-1",
    transport: {
      async write(input) {
        writes.push({
          data: input.data,
          encoding: input.encoding
        });
      }
    }
  });

  assert.deepEqual(writes, [
    {
      data: "ls\n",
      encoding: "utf8"
    },
    {
      data: "\u0003",
      encoding: "binary"
    }
  ]);
});
