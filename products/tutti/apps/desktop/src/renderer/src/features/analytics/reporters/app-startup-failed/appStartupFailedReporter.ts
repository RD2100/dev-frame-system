import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppStartupFailedParams } from "./types.ts";

export class AppStartupFailedReporter extends BaseAnalyticsReporter<AppStartupFailedParams> {
  protected readonly eventName = "app.startup_failed";

  constructor(
    params: AppStartupFailedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
