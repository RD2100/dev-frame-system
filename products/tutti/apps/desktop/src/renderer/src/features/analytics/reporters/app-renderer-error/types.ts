import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AppRendererErrorParams extends AnalyticsReporterParams {
  errorMessage: string;
  errorType: string;
  source: "unhandled_error" | "unhandled_rejection";
}
