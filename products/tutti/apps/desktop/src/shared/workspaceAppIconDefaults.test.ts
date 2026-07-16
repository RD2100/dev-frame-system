import assert from "node:assert/strict";
import test from "node:test";
import {
  tuttiAgentAssetUrls,
  tuttiIssueAssetUrls
} from "./tuttiAssetProtocol.ts";
import { resolveDesktopWorkspaceAppDefaultIconUrl } from "./workspaceAppIconDefaults.ts";

test("desktop workspace app default icon resolver maps built-in app ids", () => {
  assert.equal(
    resolveDesktopWorkspaceAppDefaultIconUrl("agent-codex"),
    tuttiAgentAssetUrls.codex
  );
  assert.equal(
    resolveDesktopWorkspaceAppDefaultIconUrl("agent-claude-code"),
    tuttiAgentAssetUrls.claudeCode
  );
  assert.equal(
    resolveDesktopWorkspaceAppDefaultIconUrl("issue-manager"),
    tuttiIssueAssetUrls.default
  );
});

test("desktop workspace app default icon resolver ignores unknown app ids", () => {
  assert.equal(resolveDesktopWorkspaceAppDefaultIconUrl("unknown"), null);
});
