import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface ErrorWorkspaceUnavailableParams extends AnalyticsReporterParams {
  errorType: string;
}
