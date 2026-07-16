import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { WorkspaceOverviewRetryClickedParams } from "./types.ts";

export class WorkspaceOverviewRetryClickedReporter extends BaseAnalyticsReporter<WorkspaceOverviewRetryClickedParams> {
  protected readonly eventName = "workspace.overview.retry_clicked";

  constructor(
    params: WorkspaceOverviewRetryClickedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
