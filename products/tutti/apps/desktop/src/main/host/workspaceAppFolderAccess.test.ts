import assert from "node:assert/strict";
import { join } from "node:path";
import test from "node:test";
import {
  resolveWorkspaceAppFolderPath,
  workspaceAppScopeSegment
} from "./workspaceAppFolderPaths.ts";

test("resolveWorkspaceAppFolderPath resolves workspace app runtime folders", () => {
  const stateRoot = "/state";
  const scope = workspaceAppScopeSegment("workspace-1", "automation.center");

  assert.equal(
    resolveWorkspaceAppFolderPath(stateRoot, {
      appId: "automation.center",
      folderKind: "workspace",
      workspaceId: "workspace-1"
    }),
    join(stateRoot, "apps", "installations", "automation.center", scope)
  );
  assert.equal(
    resolveWorkspaceAppFolderPath(stateRoot, {
      appId: "automation.center",
      folderKind: "data",
      workspaceId: "workspace-1"
    }),
    join(stateRoot, "apps", "installations", "automation.center", scope, "data")
  );
  assert.equal(
    resolveWorkspaceAppFolderPath(stateRoot, {
      appId: "automation.center",
      folderKind: "logs",
      workspaceId: "workspace-1"
    }),
    join(stateRoot, "apps", "installations", "automation.center", scope, "logs")
  );
  assert.equal(
    resolveWorkspaceAppFolderPath(stateRoot, {
      appId: "automation.center",
      folderKind: "runtime",
      workspaceId: "workspace-1"
    }),
    join(
      stateRoot,
      "apps",
      "installations",
      "automation.center",
      scope,
      "runtime"
    )
  );
});

test("resolveWorkspaceAppFolderPath resolves package folders by version", () => {
  assert.equal(
    resolveWorkspaceAppFolderPath("/state", {
      appId: "automation.center",
      folderKind: "package",
      version: "0.1.0",
      workspaceId: "workspace-1"
    }),
    join("/state", "apps", "packages", "automation.center", "0.1.0")
  );
});

test("resolveWorkspaceAppFolderPath requires package version", () => {
  assert.throws(
    () =>
      resolveWorkspaceAppFolderPath("/state", {
        appId: "automation.center",
        folderKind: "package",
        workspaceId: "workspace-1"
      }),
    /package version is required/u
  );
});
