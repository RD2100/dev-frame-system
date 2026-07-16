import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { WorkspaceCloseGuardCancelledParams } from "./types.ts";

export class WorkspaceCloseGuardCancelledReporter extends BaseAnalyticsReporter<WorkspaceCloseGuardCancelledParams> {
  protected readonly eventName = "workspace.close_guard_cancelled";

  constructor(
    params: WorkspaceCloseGuardCancelledParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
