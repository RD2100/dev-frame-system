import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentMessageSentParams } from "./types.ts";

export class AgentMessageSentReporter extends BaseAnalyticsReporter<AgentMessageSentParams> {
  protected readonly eventName = "agent.message_sent";

  constructor(
    params: AgentMessageSentParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
