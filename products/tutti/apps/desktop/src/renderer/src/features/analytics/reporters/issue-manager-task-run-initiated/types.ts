import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerTaskRunInitiatedParams extends AnalyticsReporterParams {
  hasExecutionDirectory: boolean;
  issueId: string;
  provider: string;
  taskId: string | null;
}
