import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentSettingsPermissionModeChangedParams extends AnalyticsReporterParams {
  agentSessionId: string | null;
  fromMode: string | null;
  provider: string;
  toMode: string;
}
