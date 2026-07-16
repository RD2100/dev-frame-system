import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentSettingsPermissionModeChangedParams } from "./types.ts";

export class AgentSettingsPermissionModeChangedReporter extends BaseAnalyticsReporter<AgentSettingsPermissionModeChangedParams> {
  protected readonly eventName = "agent.settings.permission_mode_changed";

  constructor(
    params: AgentSettingsPermissionModeChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
