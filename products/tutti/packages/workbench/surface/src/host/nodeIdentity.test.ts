import assert from "node:assert/strict";
import test from "node:test";
import {
  createWorkbenchHostLaunchedNodeId,
  createWorkbenchHostProjectedNodeId
} from "./nodeIdentity.ts";

test("createWorkbenchHostProjectedNodeId derives stable projected shell ids", () => {
  assert.equal(
    createWorkbenchHostProjectedNodeId({
      instanceId: "session-1",
      typeId: "terminal"
    }),
    "terminal:session-1"
  );
});

test("createWorkbenchHostLaunchedNodeId preserves singleton shell ids", () => {
  assert.equal(
    createWorkbenchHostLaunchedNodeId({
      instanceId: "workspace-files",
      typeId: "workspace-files"
    }),
    "workspace-files"
  );
  assert.equal(
    createWorkbenchHostLaunchedNodeId({
      instanceId: "browser-1",
      typeId: "browser"
    }),
    "browser:browser-1"
  );
});
