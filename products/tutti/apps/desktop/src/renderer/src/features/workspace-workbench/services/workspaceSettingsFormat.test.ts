import assert from "node:assert/strict";
import test from "node:test";
import { formatWorkspaceSettingsBytes } from "./workspaceSettingsFormat.ts";

test("formatWorkspaceSettingsBytes formats byte counts for workspace settings", () => {
  assert.equal(formatWorkspaceSettingsBytes(0), "0 B");
  assert.equal(formatWorkspaceSettingsBytes(512), "512 B");
  assert.equal(formatWorkspaceSettingsBytes(1536), "1.5 KB");
  assert.equal(formatWorkspaceSettingsBytes(10 * 1024), "10 KB");
  assert.equal(formatWorkspaceSettingsBytes(3 * 1024 * 1024), "3.0 MB");
});
