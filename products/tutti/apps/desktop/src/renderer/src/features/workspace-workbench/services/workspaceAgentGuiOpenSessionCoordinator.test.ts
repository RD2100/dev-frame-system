import assert from "node:assert/strict";
import test from "node:test";
import {
  isWorkspaceAgentGuiSessionOpen,
  registerWorkspaceAgentGuiOpenSession
} from "./workspaceAgentGuiOpenSessionCoordinator.ts";

test("workspace agent gui session is not open before registration", () => {
  assert.equal(
    isWorkspaceAgentGuiSessionOpen("workspace-1", "session-1"),
    false
  );
});

test("registering an agent gui session marks it open until released", () => {
  const release = registerWorkspaceAgentGuiOpenSession(
    "workspace-2",
    "session-2"
  );
  assert.equal(
    isWorkspaceAgentGuiSessionOpen("workspace-2", "session-2"),
    true
  );
  release();
  assert.equal(
    isWorkspaceAgentGuiSessionOpen("workspace-2", "session-2"),
    false
  );
});

test("releasing twice is a no-op", () => {
  const release = registerWorkspaceAgentGuiOpenSession(
    "workspace-3",
    "session-3"
  );
  release();
  release();
  assert.equal(
    isWorkspaceAgentGuiSessionOpen("workspace-3", "session-3"),
    false
  );
});

test("a session stays open while any registration for it is still active", () => {
  const releaseFirst = registerWorkspaceAgentGuiOpenSession(
    "workspace-4",
    "session-4"
  );
  const releaseSecond = registerWorkspaceAgentGuiOpenSession(
    "workspace-4",
    "session-4"
  );
  releaseFirst();
  assert.equal(
    isWorkspaceAgentGuiSessionOpen("workspace-4", "session-4"),
    true
  );
  releaseSecond();
  assert.equal(
    isWorkspaceAgentGuiSessionOpen("workspace-4", "session-4"),
    false
  );
});

test("different workspaces and sessions do not interfere with each other", () => {
  const release = registerWorkspaceAgentGuiOpenSession(
    "workspace-5",
    "session-5"
  );
  assert.equal(isWorkspaceAgentGuiSessionOpen("workspace-5", "other"), false);
  assert.equal(
    isWorkspaceAgentGuiSessionOpen("other-workspace", "session-5"),
    false
  );
  release();
});

test("blank workspace or session ids are ignored", () => {
  const release = registerWorkspaceAgentGuiOpenSession("  ", "session-6");
  assert.equal(isWorkspaceAgentGuiSessionOpen("  ", "session-6"), false);
  release();
});
