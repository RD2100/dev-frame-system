import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { ErrorWorkspaceUnavailableParams } from "./types.ts";

export class ErrorWorkspaceUnavailableReporter extends BaseAnalyticsReporter<ErrorWorkspaceUnavailableParams> {
  protected readonly eventName = "error.workspace_unavailable";

  constructor(
    params: ErrorWorkspaceUnavailableParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
