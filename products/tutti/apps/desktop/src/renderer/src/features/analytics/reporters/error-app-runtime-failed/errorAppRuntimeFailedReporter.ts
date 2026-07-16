import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { ErrorAppRuntimeFailedParams } from "./types.ts";

export class ErrorAppRuntimeFailedReporter extends BaseAnalyticsReporter<ErrorAppRuntimeFailedParams> {
  protected readonly eventName = "error.app_runtime_failed";

  constructor(
    params: ErrorAppRuntimeFailedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
