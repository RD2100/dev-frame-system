import assert from "node:assert/strict";
import test from "node:test";
import type { WorkspaceFileActivationTarget } from "@tutti-os/workspace-file-manager/services";
import {
  createWorkspaceFilePreviewInstanceID,
  createWorkspaceFilePreviewLaunchRequest,
  workspaceTextFileNodeTypeID
} from "./workspaceFilePreviewLaunch.ts";

function textTarget(path: string): WorkspaceFileActivationTarget {
  return {
    fileKind: "text",
    mtimeMs: null,
    name: path.split("/").pop() ?? "file.txt",
    path,
    sizeBytes: null
  };
}

test("workspace file preview instance ids are short stable path hashes", () => {
  const longPath = `/Users/example/${"nested-directory/".repeat(20)}notes.txt`;
  const target = textTarget(longPath);
  const instanceID = createWorkspaceFilePreviewInstanceID(target);

  assert.match(instanceID, /^path:[0-9a-f]{16}$/);
  assert.equal(instanceID, createWorkspaceFilePreviewInstanceID(target));
  assert.ok(!instanceID.includes(longPath));
  assert.ok(instanceID.length < 64);
});

test("workspace file preview instance ids distinguish file paths", () => {
  assert.notEqual(
    createWorkspaceFilePreviewInstanceID(textTarget("/workspace/a.txt")),
    createWorkspaceFilePreviewInstanceID(textTarget("/workspace/b.txt"))
  );
});

test("workspace file preview launch requests preserve the original file target", () => {
  const target = textTarget("/workspace/docs/spec.md");
  const request = createWorkspaceFilePreviewLaunchRequest(target);

  assert.equal(request.typeId, workspaceTextFileNodeTypeID);
  assert.equal(request.payload, target);
});
