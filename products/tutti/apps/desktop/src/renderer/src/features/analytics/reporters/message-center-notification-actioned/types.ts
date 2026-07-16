import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface MessageCenterNotificationActionedParams extends AnalyticsReporterParams {
  action: string;
  provider: string;
}
