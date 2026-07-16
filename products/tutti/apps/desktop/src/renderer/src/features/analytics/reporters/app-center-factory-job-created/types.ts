import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AppCenterFactoryJobCreatedParams extends AnalyticsReporterParams {
  readonly jobId: string;
  readonly model: string | null;
  readonly provider: string | null;
  readonly reasoningEffort: string | null;
  readonly status: string;
  readonly workspaceId: string;
}
