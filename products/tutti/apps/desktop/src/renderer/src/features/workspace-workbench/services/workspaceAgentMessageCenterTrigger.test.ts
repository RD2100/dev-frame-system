import assert from "node:assert/strict";
import test from "node:test";
import { resolveWorkspaceAgentMessageCenterTrigger } from "./workspaceAgentMessageCenterTrigger.ts";

test("workspace agent message center trigger prioritizes waiting count", () => {
  assert.deepEqual(
    resolveWorkspaceAgentMessageCenterTrigger({
      waitingCount: 2,
      runningCount: 3
    }),
    {
      count: 2,
      kind: "waiting",
      translationKey: "workspace.agentMessageCenter.waitingCount"
    }
  );
});

test("workspace agent message center trigger falls back to running count", () => {
  assert.deepEqual(
    resolveWorkspaceAgentMessageCenterTrigger({
      waitingCount: 0,
      runningCount: 3
    }),
    {
      count: 3,
      kind: "running",
      translationKey: "workspace.agentMessageCenter.runningCount"
    }
  );
});

test("workspace agent message center trigger shows waiting zero when idle", () => {
  assert.deepEqual(
    resolveWorkspaceAgentMessageCenterTrigger({
      waitingCount: 0,
      runningCount: 0
    }),
    {
      count: 0,
      kind: "waiting",
      translationKey: "workspace.agentMessageCenter.waitingCount"
    }
  );
});
