import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentMessageStoppedParams extends AnalyticsReporterParams {
  agentSessionId: string;
  provider: string;
}
