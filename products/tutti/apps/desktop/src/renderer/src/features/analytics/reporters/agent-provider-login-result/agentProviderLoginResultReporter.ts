import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentProviderLoginResultParams } from "./types.ts";

export class AgentProviderLoginResultReporter extends BaseAnalyticsReporter<AgentProviderLoginResultParams> {
  protected readonly eventName = "agent.provider_login_result";

  constructor(
    params: AgentProviderLoginResultParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
