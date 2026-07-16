import assert from "node:assert/strict";
import test from "node:test";
import { createDesktopIssueManagerShareAdapter } from "./desktopIssueManagerShareAdapter.ts";

test("desktop issue-manager share adapter creates encoded local links", async () => {
  const adapter = createDesktopIssueManagerShareAdapter();

  const issueOnly = await adapter.createIssueLink!({
    issueId: "issue 1",
    workspaceId: "workspace/1"
  });
  const issueTask = await adapter.createIssueLink!({
    issueId: "issue 1",
    taskId: "task/1",
    workspaceId: "workspace/1"
  });

  assert.equal(issueOnly, "tutti://workspace/workspace%2F1/issues/issue%201");
  assert.equal(
    issueTask,
    "tutti://workspace/workspace%2F1/issues/issue%201/tasks/task%2F1"
  );
});
