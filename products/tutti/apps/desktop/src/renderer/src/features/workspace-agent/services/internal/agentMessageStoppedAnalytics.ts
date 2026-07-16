import { AgentMessageStoppedReporter } from "../../../analytics/reporters/agent-message-stopped/agentMessageStoppedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";
import { createOptionalReporterService } from "./agentMessageSentAnalytics.ts";

export interface AgentMessageStoppedTracker {
  track(input: { agentSessionId: string; provider: string }): Promise<void>;
}

export function createAgentMessageStoppedTracker(input: {
  reporterNow?: () => number;
  reporterService?: Pick<IReporterService, "trackEvents">;
}): AgentMessageStoppedTracker {
  return {
    async track(message) {
      await new AgentMessageStoppedReporter(
        {
          agentSessionId: message.agentSessionId,
          provider: message.provider
        },
        {
          reporterService: createOptionalReporterService(input.reporterService),
          now: input.reporterNow
        }
      ).report();
    }
  };
}
