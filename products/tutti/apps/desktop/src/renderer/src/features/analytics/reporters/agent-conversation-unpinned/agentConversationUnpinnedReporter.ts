import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentConversationUnpinnedParams } from "./types.ts";

export class AgentConversationUnpinnedReporter extends BaseAnalyticsReporter<AgentConversationUnpinnedParams> {
  protected readonly eventName = "agent.conversation_unpinned";

  constructor(
    params: AgentConversationUnpinnedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
