import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface WorkspaceOpenedParams extends AnalyticsReporterParams {
  routeView: string;
}
