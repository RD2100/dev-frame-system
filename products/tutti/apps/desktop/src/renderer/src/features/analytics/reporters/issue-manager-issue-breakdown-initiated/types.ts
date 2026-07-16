import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerIssueBreakdownInitiatedParams extends AnalyticsReporterParams {
  issueId: string;
  provider: string;
}
