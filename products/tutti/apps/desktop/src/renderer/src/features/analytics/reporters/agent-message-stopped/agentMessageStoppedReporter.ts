import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentMessageStoppedParams } from "./types.ts";

export class AgentMessageStoppedReporter extends BaseAnalyticsReporter<AgentMessageStoppedParams> {
  protected readonly eventName = "agent.message_stopped";

  constructor(
    params: AgentMessageStoppedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
