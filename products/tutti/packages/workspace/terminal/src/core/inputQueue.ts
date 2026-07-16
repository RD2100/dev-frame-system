import type {
  TerminalTransport,
  TerminalWriteEncoding
} from "../contracts/index.ts";

export interface QueuedTerminalInput {
  data: string;
  encoding: TerminalWriteEncoding;
}

export interface BufferedTerminalInputQueue {
  enqueue(data: string, encoding?: TerminalWriteEncoding): void;
  flush(writer: (entry: QueuedTerminalInput) => Promise<void>): Promise<void>;
  reset(): void;
}

export function createBufferedTerminalInputQueue(): BufferedTerminalInputQueue {
  const entries: QueuedTerminalInput[] = [];

  return {
    enqueue(data, encoding = "utf8") {
      if (data.length === 0) {
        return;
      }
      entries.push({ data, encoding });
    },
    async flush(writer) {
      const queued = entries.splice(0);
      for (const entry of queued) {
        await writer(entry);
      }
    },
    reset() {
      entries.length = 0;
    }
  };
}

export async function writeQueuedTerminalInput(input: {
  queue: BufferedTerminalInputQueue;
  sessionId: string;
  transport: Pick<TerminalTransport, "write">;
}): Promise<void> {
  await input.queue.flush((entry) =>
    input.transport.write({
      data: entry.data,
      encoding: entry.encoding,
      provenance: "user",
      sessionId: input.sessionId
    })
  );
}
