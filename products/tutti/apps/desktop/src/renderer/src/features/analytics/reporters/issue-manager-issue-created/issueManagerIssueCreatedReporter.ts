import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerIssueCreatedParams } from "./types.ts";

export class IssueManagerIssueCreatedReporter extends BaseAnalyticsReporter<IssueManagerIssueCreatedParams> {
  protected readonly eventName = "issue_manager.issue_created";

  constructor(
    params: IssueManagerIssueCreatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
