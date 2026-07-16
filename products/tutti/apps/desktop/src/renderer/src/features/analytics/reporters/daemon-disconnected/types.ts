import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface DaemonDisconnectedParams extends AnalyticsReporterParams {
  reason: "process_exit" | "timeout" | "unknown";
}
