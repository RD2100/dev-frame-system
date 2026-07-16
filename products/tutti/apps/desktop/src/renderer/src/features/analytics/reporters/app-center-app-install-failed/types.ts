import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AppCenterAppInstallFailedParams extends AnalyticsReporterParams {
  readonly appId: string;
  readonly appSource: string | null;
  readonly failureReason: string | null;
}
