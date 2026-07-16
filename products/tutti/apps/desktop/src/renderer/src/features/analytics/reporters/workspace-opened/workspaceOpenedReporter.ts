import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { WorkspaceOpenedParams } from "./types.ts";

export class WorkspaceOpenedReporter extends BaseAnalyticsReporter<WorkspaceOpenedParams> {
  protected readonly eventName = "workspace.opened";

  constructor(
    params: WorkspaceOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
