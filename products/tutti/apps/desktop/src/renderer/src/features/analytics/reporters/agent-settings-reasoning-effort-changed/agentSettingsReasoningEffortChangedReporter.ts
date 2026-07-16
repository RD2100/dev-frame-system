import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentSettingsReasoningEffortChangedParams } from "./types.ts";

export class AgentSettingsReasoningEffortChangedReporter extends BaseAnalyticsReporter<AgentSettingsReasoningEffortChangedParams> {
  protected readonly eventName = "agent.settings.reasoning_effort_changed";

  constructor(
    params: AgentSettingsReasoningEffortChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
