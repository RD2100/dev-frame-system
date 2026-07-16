import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface MessageCenterOpenedParams extends AnalyticsReporterParams {
  readonly unreadCount: number;
}
