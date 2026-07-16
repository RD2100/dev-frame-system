import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerIssueSavedParams extends AnalyticsReporterParams {
  contextRefCount: number;
  hasDescription: boolean;
  issueId: string;
  taskCount: number;
}
