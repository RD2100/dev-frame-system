import type {
  IssueManagerAnalyticsAdapter,
  IssueManagerAnalyticsEvent
} from "@tutti-os/workspace-issue-manager/contracts";
import { IssueManagerContextRefAddedReporter } from "../../analytics/reporters/issue-manager-context-ref-added/issueManagerContextRefAddedReporter.ts";
import { IssueManagerContextRefRemovedReporter } from "../../analytics/reporters/issue-manager-context-ref-removed/issueManagerContextRefRemovedReporter.ts";
import { IssueManagerIssueBreakdownInitiatedReporter } from "../../analytics/reporters/issue-manager-issue-breakdown-initiated/issueManagerIssueBreakdownInitiatedReporter.ts";
import { IssueManagerIssueCreatedReporter } from "../../analytics/reporters/issue-manager-issue-created/issueManagerIssueCreatedReporter.ts";
import { IssueManagerIssueDeletedReporter } from "../../analytics/reporters/issue-manager-issue-deleted/issueManagerIssueDeletedReporter.ts";
import { IssueManagerIssueSavedReporter } from "../../analytics/reporters/issue-manager-issue-saved/issueManagerIssueSavedReporter.ts";
import { IssueManagerOpenedReporter } from "../../analytics/reporters/issue-manager-opened/issueManagerOpenedReporter.ts";
import { IssueManagerTaskCreatedReporter } from "../../analytics/reporters/issue-manager-task-created/issueManagerTaskCreatedReporter.ts";
import { IssueManagerTaskDeletedReporter } from "../../analytics/reporters/issue-manager-task-deleted/issueManagerTaskDeletedReporter.ts";
import { IssueManagerTaskRunInitiatedReporter } from "../../analytics/reporters/issue-manager-task-run-initiated/issueManagerTaskRunInitiatedReporter.ts";
import { IssueManagerTaskSavedReporter } from "../../analytics/reporters/issue-manager-task-saved/issueManagerTaskSavedReporter.ts";
import { IssueManagerTaskSearchedReporter } from "../../analytics/reporters/issue-manager-task-searched/issueManagerTaskSearchedReporter.ts";
import { IssueManagerTopicChangedReporter } from "../../analytics/reporters/issue-manager-topic-changed/issueManagerTopicChangedReporter.ts";
import type { IReporterService } from "../../analytics/services/reporterService.interface.ts";

export function createDesktopIssueManagerAnalytics(input: {
  reporterNow?: () => number;
  reporterService?: Pick<IReporterService, "trackEvents">;
}): IssueManagerAnalyticsAdapter | undefined {
  const reporterService = input.reporterService;
  if (!reporterService) {
    return undefined;
  }
  return {
    track(event) {
      return reportIssueManagerAnalyticsEvent(event, {
        reporterNow: input.reporterNow,
        reporterService
      });
    }
  };
}

function reportIssueManagerAnalyticsEvent(
  event: IssueManagerAnalyticsEvent,
  dependencies: {
    reporterNow?: () => number;
    reporterService: Pick<IReporterService, "trackEvents">;
  }
): Promise<void> {
  const reporterDependencies = {
    now: dependencies.reporterNow,
    reporterService: dependencies.reporterService
  };
  switch (event.name) {
    case "issue_manager.opened":
      return new IssueManagerOpenedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.issue_created":
      return new IssueManagerIssueCreatedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.issue_saved":
      return new IssueManagerIssueSavedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.issue_deleted":
      return new IssueManagerIssueDeletedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.task_created":
      return new IssueManagerTaskCreatedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.task_saved":
      return new IssueManagerTaskSavedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.task_deleted":
      return new IssueManagerTaskDeletedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.task_run_initiated":
      return new IssueManagerTaskRunInitiatedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.issue_breakdown_initiated":
      return new IssueManagerIssueBreakdownInitiatedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.context_ref_added":
      return new IssueManagerContextRefAddedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.context_ref_removed":
      return new IssueManagerContextRefRemovedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.topic_changed":
      return new IssueManagerTopicChangedReporter(
        event.params,
        reporterDependencies
      ).report();
    case "issue_manager.task_searched":
      return new IssueManagerTaskSearchedReporter(
        event.params,
        reporterDependencies
      ).report();
  }
}
