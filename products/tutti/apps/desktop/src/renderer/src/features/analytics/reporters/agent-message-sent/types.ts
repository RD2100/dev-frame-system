import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AgentMessageSentParams extends AnalyticsReporterParams {
  agentSessionId: string;
  conversationIndex: number;
  hasFileMention: boolean;
  hasSlashCommand: boolean;
  isQueued: boolean;
  provider: string;
}
