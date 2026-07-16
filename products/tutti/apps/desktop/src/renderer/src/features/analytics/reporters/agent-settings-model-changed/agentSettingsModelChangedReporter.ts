import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentSettingsModelChangedParams } from "./types.ts";

export class AgentSettingsModelChangedReporter extends BaseAnalyticsReporter<AgentSettingsModelChangedParams> {
  protected readonly eventName = "agent.settings.model_changed";

  constructor(
    params: AgentSettingsModelChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
