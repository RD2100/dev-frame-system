import type { TerminalDiagnostics } from "../contracts/index.ts";

export interface TerminalCloseDiagnostics {
  confirmed(): void;
  requested(): void;
}

export interface TerminalSurfaceDiagnostics {
  dispose(): void;
  mount(): void;
  outputSync(input: {
    contentEpoch: number;
    nextCommittedBytes: number;
    plan: "append" | "replace" | "reset" | "skip";
    previousCommittedBytes: number;
    rawBytes: number;
    writeBytes: number;
  }): void;
  outputWritten(input: {
    bufferCursorX: number;
    bufferCursorY: number;
    bufferLength: number;
    bytes: number;
    canvasClientHeight: number;
    canvasClientWidth: number;
    canvasCount: number;
    cols: number;
    containerClientHeight: number;
    containerClientWidth: number;
    cursorLinePreview: string;
    firstLinePreview: string;
    helperChildCount: number;
    mode: "append" | "cache" | "replace" | "reset";
    remainingChunkCount: number;
    renderDimensionsReady: boolean;
    rowContainerChildCount: number;
    rowContainerTextPreview: string;
    rows: number;
    screenChildCount: number;
    screenClientHeight: number;
    screenClientWidth: number;
    screenDisplay: string;
    screenOpacity: string;
    screenVisibility: string;
    serializedBytes: number;
    xtermClientHeight: number;
    xtermClientWidth: number;
    xtermDisplay: string;
    xtermOpacity: string;
    xtermVisibility: string;
  }): void;
  resize(input: { cols: number; rows: number }): void;
}

export interface TerminalSessionRecoveryDiagnostics {
  attachComplete(): void;
  attachError(): void;
  attachStart(afterSeq: number | null): void;
  hydrationComplete(replayChunkCount: number): void;
  hydrationGap(input: { fromSeq: number; toSeq: number }): void;
  hydrationStart(): void;
  outputProjected(input: {
    contentEpoch: number;
    previewHead: string;
    previewTail: string;
    rawBytes: number;
    source: "replay" | "snapshot";
    writeBytes: number;
  }): void;
  snapshotComplete(input: { toSeq: number | null; truncated: boolean }): void;
  snapshotStart(): void;
}

export function createTerminalSurfaceDiagnostics(input: {
  diagnostics: TerminalDiagnostics;
  nodeId: string;
  sessionId: string;
}): TerminalSurfaceDiagnostics {
  return {
    dispose() {
      input.diagnostics.log("dispose", resolveContext(input));
    },
    mount() {
      input.diagnostics.log("mount", resolveContext(input));
    },
    outputSync({
      contentEpoch,
      nextCommittedBytes,
      plan,
      previousCommittedBytes,
      rawBytes,
      writeBytes
    }) {
      input.diagnostics.log("surface-output-sync", {
        ...resolveContext(input),
        contentEpoch,
        nextCommittedBytes,
        plan,
        previousCommittedBytes,
        rawBytes,
        writeBytes
      });
    },
    outputWritten({
      bufferCursorX,
      bufferCursorY,
      bufferLength,
      bytes,
      canvasClientHeight,
      canvasClientWidth,
      canvasCount,
      cols,
      containerClientHeight,
      containerClientWidth,
      cursorLinePreview,
      firstLinePreview,
      helperChildCount,
      mode,
      remainingChunkCount,
      renderDimensionsReady,
      rowContainerChildCount,
      rowContainerTextPreview,
      rows,
      screenChildCount,
      screenClientHeight,
      screenClientWidth,
      screenDisplay,
      screenOpacity,
      screenVisibility,
      serializedBytes,
      xtermClientHeight,
      xtermClientWidth,
      xtermDisplay,
      xtermOpacity,
      xtermVisibility
    }) {
      input.diagnostics.log("surface-output-written", {
        ...resolveContext(input),
        bufferCursorX,
        bufferCursorY,
        bufferLength,
        bytes,
        canvasClientHeight,
        canvasClientWidth,
        canvasCount,
        cols,
        containerClientHeight,
        containerClientWidth,
        cursorLinePreview,
        firstLinePreview,
        helperChildCount,
        mode,
        remainingChunkCount,
        renderDimensionsReady,
        rowContainerChildCount,
        rowContainerTextPreview,
        rows,
        screenChildCount,
        screenClientHeight,
        screenClientWidth,
        screenDisplay,
        screenOpacity,
        screenVisibility,
        serializedBytes,
        xtermClientHeight,
        xtermClientWidth,
        xtermDisplay,
        xtermOpacity,
        xtermVisibility
      });
    },
    resize({ cols, rows }) {
      input.diagnostics.log("resize", {
        ...resolveContext(input),
        cols,
        rows
      });
    }
  };
}

export function createTerminalCloseDiagnostics(input: {
  diagnostics: TerminalDiagnostics;
  sessionId: string;
}): TerminalCloseDiagnostics {
  return {
    confirmed() {
      input.diagnostics.log("close-confirmed", {
        sessionId: input.sessionId
      });
    },
    requested() {
      input.diagnostics.log("close-requested", {
        sessionId: input.sessionId
      });
    }
  };
}

export function createTerminalSessionRecoveryDiagnostics(input: {
  diagnostics: TerminalDiagnostics;
  nodeId: string;
  sessionId: string;
}): TerminalSessionRecoveryDiagnostics {
  return {
    attachComplete() {
      input.diagnostics.log("attach-complete", resolveContext(input));
    },
    attachError() {
      input.diagnostics.log("attach-error", resolveContext(input));
    },
    attachStart(afterSeq) {
      input.diagnostics.log("attach-start", {
        ...resolveContext(input),
        afterSeq
      });
    },
    hydrationComplete(replayChunkCount) {
      input.diagnostics.log("hydration-complete", {
        ...resolveContext(input),
        replayChunkCount
      });
    },
    hydrationGap({ fromSeq, toSeq }) {
      input.diagnostics.log("hydration-gap", {
        ...resolveContext(input),
        fromSeq,
        toSeq
      });
    },
    hydrationStart() {
      input.diagnostics.log("hydration-start", resolveContext(input));
    },
    outputProjected({
      contentEpoch,
      previewHead,
      previewTail,
      rawBytes,
      source,
      writeBytes
    }) {
      input.diagnostics.log("output-projected", {
        ...resolveContext(input),
        contentEpoch,
        previewHead,
        previewTail,
        rawBytes,
        source,
        writeBytes
      });
    },
    snapshotComplete({ toSeq, truncated }) {
      input.diagnostics.log("snapshot-complete", {
        ...resolveContext(input),
        toSeq,
        truncated
      });
    },
    snapshotStart() {
      input.diagnostics.log("snapshot-start", resolveContext(input));
    }
  };
}

function resolveContext(input: { nodeId: string; sessionId: string }) {
  return {
    nodeId: input.nodeId,
    sessionId: input.sessionId
  };
}
