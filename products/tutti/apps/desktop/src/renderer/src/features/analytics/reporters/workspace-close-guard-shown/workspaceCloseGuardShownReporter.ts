import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { WorkspaceCloseGuardShownParams } from "./types.ts";

export class WorkspaceCloseGuardShownReporter extends BaseAnalyticsReporter<WorkspaceCloseGuardShownParams> {
  protected readonly eventName = "workspace.close_guard_shown";

  constructor(
    params: WorkspaceCloseGuardShownParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
