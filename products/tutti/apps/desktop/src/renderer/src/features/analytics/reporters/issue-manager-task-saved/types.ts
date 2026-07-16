import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerTaskSavedParams extends AnalyticsReporterParams {
  contextRefCount: number;
  hasDescription: boolean;
  issueId: string;
  taskId: string;
}
