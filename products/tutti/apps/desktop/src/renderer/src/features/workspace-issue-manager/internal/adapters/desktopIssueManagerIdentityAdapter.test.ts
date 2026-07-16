import assert from "node:assert/strict";
import test from "node:test";
import { createDesktopIssueManagerIdentityAdapter } from "./desktopIssueManagerIdentityAdapter.ts";

test("desktop issue-manager identity adapter returns local placeholder identity", () => {
  const adapter = createDesktopIssueManagerIdentityAdapter();

  assert.deepEqual(adapter.currentUser(), {
    displayName: "Local",
    userId: "local"
  });
});
