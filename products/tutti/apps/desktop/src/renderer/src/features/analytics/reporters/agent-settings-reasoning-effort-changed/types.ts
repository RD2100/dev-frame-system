import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentSettingsReasoningEffortChangedParams extends AnalyticsReporterParams {
  agentSessionId: string | null;
  fromEffort: string | null;
  provider: string;
  toEffort: string;
}
