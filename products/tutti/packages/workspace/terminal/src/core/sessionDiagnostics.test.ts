import assert from "node:assert/strict";
import test from "node:test";
import type { TerminalDiagnosticEvent } from "../contracts/index.ts";
import {
  createTerminalCloseDiagnostics,
  createTerminalSessionRecoveryDiagnostics,
  createTerminalSurfaceDiagnostics
} from "./sessionDiagnostics.ts";

test("terminal diagnostics helpers emit consistent close, surface, and recovery events", () => {
  const events: Array<{
    details: Record<string, string | number | boolean | null> | undefined;
    event: TerminalDiagnosticEvent;
  }> = [];
  const diagnostics = {
    log(
      event: TerminalDiagnosticEvent,
      details?: Record<string, string | number | boolean | null>
    ) {
      events.push({ details, event });
    }
  };

  const closeDiagnostics = createTerminalCloseDiagnostics({
    diagnostics,
    sessionId: "session-1"
  });
  const surfaceDiagnostics = createTerminalSurfaceDiagnostics({
    diagnostics,
    nodeId: "node-1",
    sessionId: "session-1"
  });
  const recoveryDiagnostics = createTerminalSessionRecoveryDiagnostics({
    diagnostics,
    nodeId: "node-1",
    sessionId: "session-1"
  });

  closeDiagnostics.requested();
  closeDiagnostics.confirmed();
  surfaceDiagnostics.mount();
  surfaceDiagnostics.outputSync({
    contentEpoch: 1,
    nextCommittedBytes: 352,
    plan: "replace",
    previousCommittedBytes: 0,
    rawBytes: 352,
    writeBytes: 352
  });
  surfaceDiagnostics.outputWritten({
    bufferCursorX: 14,
    bufferCursorY: 5,
    bufferLength: 6,
    bytes: 352,
    canvasClientHeight: 480,
    canvasClientWidth: 1024,
    canvasCount: 2,
    cols: 105,
    containerClientHeight: 520,
    containerClientWidth: 1080,
    cursorLinePreview: "➜ 705aigc.com_nginx",
    firstLinePreview: "➜ 705aigc.com_nginx",
    helperChildCount: 1,
    mode: "replace",
    remainingChunkCount: 0,
    renderDimensionsReady: true,
    rowContainerChildCount: 30,
    rowContainerTextPreview: "➜ 705aigc.com_nginx",
    rows: 30,
    screenChildCount: 3,
    screenClientHeight: 480,
    screenClientWidth: 1024,
    screenDisplay: "block",
    screenOpacity: "1",
    screenVisibility: "visible",
    serializedBytes: 352,
    xtermClientHeight: 500,
    xtermClientWidth: 1040,
    xtermDisplay: "block",
    xtermOpacity: "1",
    xtermVisibility: "visible"
  });
  surfaceDiagnostics.resize({ cols: 120, rows: 40 });
  surfaceDiagnostics.dispose();
  recoveryDiagnostics.hydrationStart();
  recoveryDiagnostics.snapshotStart();
  recoveryDiagnostics.outputProjected({
    contentEpoch: 1,
    previewHead: "\\u001b]633;C\\u0007\\u001b[?2004h",
    previewTail: "➜ 705aigc.com_nginx ",
    rawBytes: 352,
    source: "snapshot",
    writeBytes: 352
  });
  recoveryDiagnostics.snapshotComplete({ toSeq: 9, truncated: false });
  recoveryDiagnostics.attachStart(9);
  recoveryDiagnostics.outputProjected({
    contentEpoch: 1,
    previewHead: "abc",
    previewTail: "xyz",
    rawBytes: 368,
    source: "replay",
    writeBytes: 16
  });
  recoveryDiagnostics.attachComplete();
  recoveryDiagnostics.hydrationComplete(2);
  recoveryDiagnostics.hydrationGap({ fromSeq: 8, toSeq: 9 });
  recoveryDiagnostics.attachError();

  assert.deepEqual(events, [
    { details: { sessionId: "session-1" }, event: "close-requested" },
    { details: { sessionId: "session-1" }, event: "close-confirmed" },
    {
      details: { nodeId: "node-1", sessionId: "session-1" },
      event: "mount"
    },
    {
      details: {
        contentEpoch: 1,
        nextCommittedBytes: 352,
        nodeId: "node-1",
        plan: "replace",
        previousCommittedBytes: 0,
        rawBytes: 352,
        sessionId: "session-1",
        writeBytes: 352
      },
      event: "surface-output-sync"
    },
    {
      details: {
        bufferCursorX: 14,
        bufferCursorY: 5,
        bufferLength: 6,
        bytes: 352,
        canvasClientHeight: 480,
        canvasClientWidth: 1024,
        canvasCount: 2,
        cols: 105,
        containerClientHeight: 520,
        containerClientWidth: 1080,
        cursorLinePreview: "➜ 705aigc.com_nginx",
        firstLinePreview: "➜ 705aigc.com_nginx",
        helperChildCount: 1,
        mode: "replace",
        nodeId: "node-1",
        remainingChunkCount: 0,
        renderDimensionsReady: true,
        rowContainerChildCount: 30,
        rowContainerTextPreview: "➜ 705aigc.com_nginx",
        rows: 30,
        screenChildCount: 3,
        sessionId: "session-1",
        screenClientHeight: 480,
        screenClientWidth: 1024,
        screenDisplay: "block",
        screenOpacity: "1",
        screenVisibility: "visible",
        serializedBytes: 352,
        xtermClientHeight: 500,
        xtermClientWidth: 1040,
        xtermDisplay: "block",
        xtermOpacity: "1",
        xtermVisibility: "visible"
      },
      event: "surface-output-written"
    },
    {
      details: {
        cols: 120,
        nodeId: "node-1",
        rows: 40,
        sessionId: "session-1"
      },
      event: "resize"
    },
    {
      details: { nodeId: "node-1", sessionId: "session-1" },
      event: "dispose"
    },
    {
      details: { nodeId: "node-1", sessionId: "session-1" },
      event: "hydration-start"
    },
    {
      details: { nodeId: "node-1", sessionId: "session-1" },
      event: "snapshot-start"
    },
    {
      details: {
        contentEpoch: 1,
        nodeId: "node-1",
        previewHead: "\\u001b]633;C\\u0007\\u001b[?2004h",
        previewTail: "➜ 705aigc.com_nginx ",
        rawBytes: 352,
        sessionId: "session-1",
        source: "snapshot",
        writeBytes: 352
      },
      event: "output-projected"
    },
    {
      details: {
        nodeId: "node-1",
        sessionId: "session-1",
        toSeq: 9,
        truncated: false
      },
      event: "snapshot-complete"
    },
    {
      details: { afterSeq: 9, nodeId: "node-1", sessionId: "session-1" },
      event: "attach-start"
    },
    {
      details: {
        contentEpoch: 1,
        nodeId: "node-1",
        previewHead: "abc",
        previewTail: "xyz",
        rawBytes: 368,
        sessionId: "session-1",
        source: "replay",
        writeBytes: 16
      },
      event: "output-projected"
    },
    {
      details: { nodeId: "node-1", sessionId: "session-1" },
      event: "attach-complete"
    },
    {
      details: {
        nodeId: "node-1",
        replayChunkCount: 2,
        sessionId: "session-1"
      },
      event: "hydration-complete"
    },
    {
      details: {
        fromSeq: 8,
        nodeId: "node-1",
        sessionId: "session-1",
        toSeq: 9
      },
      event: "hydration-gap"
    },
    {
      details: { nodeId: "node-1", sessionId: "session-1" },
      event: "attach-error"
    }
  ]);
});
