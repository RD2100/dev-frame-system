import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentConversationPinnedParams extends AnalyticsReporterParams {
  agentSessionId: string;
  provider: string;
}
