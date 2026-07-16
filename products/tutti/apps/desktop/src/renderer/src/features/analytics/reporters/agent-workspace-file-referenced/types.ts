import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentWorkspaceFileReferencedParams extends AnalyticsReporterParams {
  hasDirectory: boolean;
  provider: string;
  referenceCount: number;
}
