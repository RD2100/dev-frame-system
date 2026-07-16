import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentSessionStartedParams } from "./types.ts";

export class AgentSessionStartedReporter extends BaseAnalyticsReporter<AgentSessionStartedParams> {
  protected readonly eventName = "agent.session_started";

  constructor(
    params: AgentSessionStartedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
