import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface ErrorAppRuntimeFailedParams extends AnalyticsReporterParams {
  appId: string;
  appSource: string;
  failureReason: string | null;
}
