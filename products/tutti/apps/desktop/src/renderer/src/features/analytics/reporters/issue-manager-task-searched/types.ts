import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerTaskSearchedParams extends AnalyticsReporterParams {
  queryLength: number;
  resultCount: number;
}
