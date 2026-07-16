import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerIssueDeletedParams extends AnalyticsReporterParams {
  issueId: string;
}
