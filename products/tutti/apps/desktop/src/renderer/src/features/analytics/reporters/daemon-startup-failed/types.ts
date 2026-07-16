import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface DaemonStartupFailedParams extends AnalyticsReporterParams {
  errorMessage: string;
  errorType: string;
}
