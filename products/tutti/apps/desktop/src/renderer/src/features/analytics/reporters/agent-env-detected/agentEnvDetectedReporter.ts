import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentEnvDetectedParams } from "./types.ts";

export class AgentEnvDetectedReporter extends BaseAnalyticsReporter<AgentEnvDetectedParams> {
  protected readonly eventName = "agent.env_detected";

  constructor(
    params: AgentEnvDetectedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
