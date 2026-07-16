import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { WorkspaceCloseGuardConfirmedParams } from "./types.ts";

export class WorkspaceCloseGuardConfirmedReporter extends BaseAnalyticsReporter<WorkspaceCloseGuardConfirmedParams> {
  protected readonly eventName = "workspace.close_guard_confirmed";

  constructor(
    params: WorkspaceCloseGuardConfirmedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
