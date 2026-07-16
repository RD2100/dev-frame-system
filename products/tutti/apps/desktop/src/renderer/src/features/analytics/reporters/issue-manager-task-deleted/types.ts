import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerTaskDeletedParams extends AnalyticsReporterParams {
  issueId: string;
  taskId: string;
}
