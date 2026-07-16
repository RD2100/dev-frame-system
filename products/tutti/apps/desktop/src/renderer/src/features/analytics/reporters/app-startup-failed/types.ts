import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AppStartupFailedParams extends AnalyticsReporterParams {
  errorMessage: string;
  errorType: string;
  process: "main" | "renderer";
}
