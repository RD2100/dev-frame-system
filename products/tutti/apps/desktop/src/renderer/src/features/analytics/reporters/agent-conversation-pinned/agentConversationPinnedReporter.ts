import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentConversationPinnedParams } from "./types.ts";

export class AgentConversationPinnedReporter extends BaseAnalyticsReporter<AgentConversationPinnedParams> {
  protected readonly eventName = "agent.conversation_pinned";

  constructor(
    params: AgentConversationPinnedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
