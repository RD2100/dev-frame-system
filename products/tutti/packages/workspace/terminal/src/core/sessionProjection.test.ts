import assert from "node:assert/strict";
import test from "node:test";
import type { TerminalNodeExternalState } from "../contracts/index.ts";
import {
  applyTerminalSessionStatusProjection,
  applyTerminalSessionTitleProjection,
  createTerminalSessionExitProjection,
  createTerminalSessionFailedProjection
} from "./sessionProjection.ts";

const baseState: TerminalNodeExternalState = {
  createdAt: null,
  cwd: null,
  endedAt: null,
  host: null,
  lastError: null,
  profileId: null,
  runtimeKind: "local",
  sessionId: "session-1",
  status: "running",
  title: "Terminal",
  updatedAt: null
};

test("applyTerminalSessionStatusProjection marks ended sessions once", () => {
  const exited = applyTerminalSessionStatusProjection(
    baseState,
    createTerminalSessionExitProjection(),
    () => "2026-05-25T00:00:00.000Z"
  );

  assert.equal(exited.status, "exited");
  assert.equal(exited.endedAt, "2026-05-25T00:00:00.000Z");

  const ignoredRestart = applyTerminalSessionStatusProjection(exited, {
    lastError: null,
    status: "running"
  });

  assert.equal(ignoredRestart, exited);
});

test("applyTerminalSessionStatusProjection records failure details", () => {
  const failed = applyTerminalSessionStatusProjection(
    baseState,
    createTerminalSessionFailedProjection("lost"),
    () => "2026-05-25T00:00:00.000Z"
  );

  assert.equal(failed.status, "failed");
  assert.equal(failed.lastError, "lost");
  assert.equal(failed.endedAt, "2026-05-25T00:00:00.000Z");
});

test("applyTerminalSessionTitleProjection updates only the title", () => {
  const renamed = applyTerminalSessionTitleProjection(baseState, "Build");

  assert.equal(renamed.title, "Build");
  assert.equal(renamed.sessionId, baseState.sessionId);
});
