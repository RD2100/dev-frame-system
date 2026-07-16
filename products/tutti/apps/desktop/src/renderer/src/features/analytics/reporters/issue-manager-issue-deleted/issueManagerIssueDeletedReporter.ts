import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerIssueDeletedParams } from "./types.ts";

export class IssueManagerIssueDeletedReporter extends BaseAnalyticsReporter<IssueManagerIssueDeletedParams> {
  protected readonly eventName = "issue_manager.issue_deleted";

  constructor(
    params: IssueManagerIssueDeletedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
