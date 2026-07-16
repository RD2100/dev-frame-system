import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentSettingsModelChangedParams extends AnalyticsReporterParams {
  agentSessionId: string | null;
  isCustomModel: boolean;
  provider: string;
}
