import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerIssueBreakdownInitiatedParams } from "./types.ts";

export class IssueManagerIssueBreakdownInitiatedReporter extends BaseAnalyticsReporter<IssueManagerIssueBreakdownInitiatedParams> {
  protected readonly eventName = "issue_manager.issue_breakdown_initiated";

  constructor(
    params: IssueManagerIssueBreakdownInitiatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
