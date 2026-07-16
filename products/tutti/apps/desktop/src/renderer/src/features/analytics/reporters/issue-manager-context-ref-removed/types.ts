import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerContextRefRemovedParams extends AnalyticsReporterParams {
  targetType: "issue" | "task";
}
