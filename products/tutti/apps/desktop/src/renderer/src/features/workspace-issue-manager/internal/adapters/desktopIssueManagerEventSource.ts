import type { TuttidEventStreamClient } from "@tutti-os/client-tuttid-ts";
import type { IssueManagerEventSource } from "@tutti-os/workspace-issue-manager/contracts";

export function createDesktopIssueManagerEventSource(
  eventStreamClient: TuttidEventStreamClient
): IssueManagerEventSource {
  return {
    connect() {
      return eventStreamClient.connect();
    },
    subscribeToIssueUpdates(workspaceId, listener) {
      return eventStreamClient.subscribe(
        "workspace.issue.updated",
        (event) => {
          listener({
            changeKind: event.payload.changeKind,
            issueId: event.payload.issueId,
            runId: event.payload.runId,
            taskId: event.payload.taskId,
            workspaceId: event.payload.workspaceId
          });
        },
        { scope: { workspaceId } }
      );
    }
  };
}
