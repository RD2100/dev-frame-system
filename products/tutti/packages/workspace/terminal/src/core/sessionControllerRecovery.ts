import type { BufferedTerminalInputQueue } from "./inputQueue.ts";
import { writeQueuedTerminalInput } from "./inputQueue.ts";
import type { TerminalTransport } from "../contracts/index.ts";
import type { TerminalSessionRecoveryDiagnostics } from "./sessionDiagnostics.ts";
import type { TerminalSessionControllerStore } from "./sessionControllerStore.ts";
import type { TerminalSessionTransportRuntime } from "./sessionTransportRuntime.ts";

export interface TerminalSessionRecoveryHandle {
  dispose(): void;
  start(): Promise<void>;
}

export function createTerminalSessionRecovery(input: {
  diagnostics: TerminalSessionRecoveryDiagnostics;
  inputQueue: BufferedTerminalInputQueue;
  onRecoverableDetach: () => void;
  onWriteReadyChange: (ready: boolean) => void;
  replayGapMessage: string;
  sessionId: string;
  snapshotTruncatedMessage: string;
  store: TerminalSessionControllerStore;
  transport: TerminalTransport;
  transportRuntime: TerminalSessionTransportRuntime;
}): TerminalSessionRecoveryHandle {
  let disposed = false;
  let hydrationReady = false;
  const hydrationReplayChunks: string[] = [];

  const disposeData = input.transportRuntime.onData((event) => {
    if (disposed || event.sessionId !== input.sessionId) {
      return;
    }
    if (!hydrationReady) {
      hydrationReplayChunks.push(event.data);
      return;
    }
    input.store.appendRawOutput(event.data);
  });

  const disposeState = input.transportRuntime.onState((event) => {
    if (disposed || event.sessionId !== input.sessionId) {
      return;
    }
    if (
      typeof event.gapStartSeq === "number" &&
      typeof event.gapEndSeq === "number"
    ) {
      input.diagnostics.hydrationGap({
        fromSeq: event.gapStartSeq,
        toSeq: event.gapEndSeq
      });
      input.store.setSurfaceError(input.replayGapMessage);
      return;
    }
    if (event.error) {
      input.store.setSurfaceError(event.error);
    }
    if (event.status === "detached") {
      input.onWriteReadyChange(false);
      input.store.setInputReady(false);
      input.onRecoverableDetach();
      return;
    }
    if (event.status === "exited") {
      input.onWriteReadyChange(false);
      input.store.setInputReady(false);
    }
  });

  const disposeExit = input.transportRuntime.onExit((event) => {
    if (disposed || event.sessionId !== input.sessionId) {
      return;
    }
    input.onWriteReadyChange(false);
    input.store.setInputReady(false);
  });

  const disposeMetadata = input.transportRuntime.onMetadata(() => undefined);

  return {
    dispose() {
      if (disposed) {
        return;
      }
      disposed = true;
      hydrationReady = false;
      hydrationReplayChunks.length = 0;
      disposeData();
      disposeState();
      disposeExit();
      disposeMetadata();
    },
    async start() {
      input.diagnostics.hydrationStart();
      input.diagnostics.snapshotStart();

      try {
        const snapshot = await input.transportRuntime.snapshot();
        if (disposed) {
          return;
        }
        input.store.replaceRawOutput(snapshot.data);
        const snapshotState = input.store.getState();
        input.diagnostics.outputProjected({
          contentEpoch: snapshotState.contentEpoch,
          previewHead: previewTerminalOutput(snapshot.data, "head"),
          previewTail: previewTerminalOutput(snapshot.data, "tail"),
          rawBytes: snapshotState.rawOutput.length,
          source: "snapshot",
          writeBytes: snapshot.data.length
        });
        if (snapshot.truncated) {
          input.store.setSurfaceError(input.snapshotTruncatedMessage);
        } else {
          input.store.setSurfaceError(null);
        }
        input.diagnostics.snapshotComplete({
          toSeq: snapshot.toSeq ?? null,
          truncated: snapshot.truncated ?? false
        });
        input.diagnostics.attachStart(snapshot.toSeq ?? null);
        await input.transportRuntime.attach(snapshot.toSeq);
        if (disposed) {
          return;
        }
        hydrationReady = true;
        const replayChunks = hydrationReplayChunks.splice(0);
        replayChunks.forEach((chunk) => {
          input.store.appendRawOutput(chunk);
        });
        if (replayChunks.length > 0) {
          const replayState = input.store.getState();
          input.diagnostics.outputProjected({
            contentEpoch: replayState.contentEpoch,
            previewHead: previewTerminalOutput(replayChunks.join(""), "head"),
            previewTail: previewTerminalOutput(replayChunks.join(""), "tail"),
            rawBytes: replayState.rawOutput.length,
            source: "replay",
            writeBytes: replayChunks.reduce(
              (total, chunk) => total + chunk.length,
              0
            )
          });
        }
        input.onWriteReadyChange(true);
        input.store.setInputReady(true);
        await writeQueuedTerminalInput({
          queue: input.inputQueue,
          sessionId: input.sessionId,
          transport: input.transport
        });
        if (disposed) {
          return;
        }
        input.diagnostics.attachComplete();
        input.diagnostics.hydrationComplete(replayChunks.length);
      } catch (error) {
        if (disposed) {
          return;
        }
        input.diagnostics.attachError();
        input.store.setSurfaceError(errorMessage(error));
      }
    }
  };
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function previewTerminalOutput(
  value: string,
  side: "head" | "tail",
  maxChars = 48
) {
  const slice =
    side === "head"
      ? value.slice(0, maxChars)
      : value.slice(Math.max(0, value.length - maxChars));
  return slice
    .replaceAll("\\", "\\\\")
    .replaceAll("\r", "\\r")
    .replaceAll("\n", "\\n");
}
