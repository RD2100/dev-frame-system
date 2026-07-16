import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentConversationUnpinnedParams extends AnalyticsReporterParams {
  agentSessionId: string;
  provider: string;
}
