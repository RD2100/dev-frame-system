import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerIssueCreatedParams extends AnalyticsReporterParams {
  issueId: string;
}
