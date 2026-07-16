import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface DaemonReconnectedParams extends AnalyticsReporterParams {
  downtimeMs: number;
}
