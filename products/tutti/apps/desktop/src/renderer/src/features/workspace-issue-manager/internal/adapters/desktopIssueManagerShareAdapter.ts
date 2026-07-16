import type { IssueManagerShareAdapter } from "@tutti-os/workspace-issue-manager/contracts";

export function createDesktopIssueManagerShareAdapter(): IssueManagerShareAdapter {
  return {
    createIssueLink(input) {
      const base = `tutti://workspace/${encodeURIComponent(input.workspaceId)}/issues/${encodeURIComponent(input.issueId)}`;
      return Promise.resolve(
        input.taskId
          ? `${base}/tasks/${encodeURIComponent(input.taskId)}`
          : base
      );
    }
  };
}
