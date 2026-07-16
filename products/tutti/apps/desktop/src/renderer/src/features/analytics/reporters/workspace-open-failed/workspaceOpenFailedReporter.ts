import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { WorkspaceOpenFailedParams } from "./types.ts";

export class WorkspaceOpenFailedReporter extends BaseAnalyticsReporter<WorkspaceOpenFailedParams> {
  protected readonly eventName = "workspace.open_failed";

  constructor(
    params: WorkspaceOpenFailedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
