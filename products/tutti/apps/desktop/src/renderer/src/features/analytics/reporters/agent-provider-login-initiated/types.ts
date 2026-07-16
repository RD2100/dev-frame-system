import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentProviderLoginInitiatedParams extends AnalyticsReporterParams {
  provider: string;
}
