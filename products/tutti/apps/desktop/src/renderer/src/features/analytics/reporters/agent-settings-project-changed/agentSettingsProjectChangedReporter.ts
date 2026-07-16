import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentSettingsProjectChangedParams } from "./types.ts";

export class AgentSettingsProjectChangedReporter extends BaseAnalyticsReporter<AgentSettingsProjectChangedParams> {
  protected readonly eventName = "agent.settings.project_changed";

  constructor(
    params: AgentSettingsProjectChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
