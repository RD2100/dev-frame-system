import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentProviderLoginInitiatedParams } from "./types.ts";

export class AgentProviderLoginInitiatedReporter extends BaseAnalyticsReporter<AgentProviderLoginInitiatedParams> {
  protected readonly eventName = "agent.provider_login_initiated";

  constructor(
    params: AgentProviderLoginInitiatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
