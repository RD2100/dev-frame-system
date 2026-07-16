import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentSessionStartedParams extends AnalyticsReporterParams {
  agentSessionId: string;
  hasCustomModel: boolean;
  hasProject: boolean;
  permissionMode: string | null;
  provider: string;
  source: string;
}
