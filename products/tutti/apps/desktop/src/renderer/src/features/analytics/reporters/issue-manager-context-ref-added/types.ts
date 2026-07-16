import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerContextRefAddedParams extends AnalyticsReporterParams {
  refType: "directory" | "file" | "upload";
  targetType: "issue" | "task";
}
