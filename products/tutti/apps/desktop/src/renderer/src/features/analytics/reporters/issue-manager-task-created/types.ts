import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerTaskCreatedParams extends AnalyticsReporterParams {
  issueId: string;
  taskId: string;
}
