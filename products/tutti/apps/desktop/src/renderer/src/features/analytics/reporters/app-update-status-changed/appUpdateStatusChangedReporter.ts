import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppUpdateStatusChangedParams } from "./types.ts";

export class AppUpdateStatusChangedReporter extends BaseAnalyticsReporter<AppUpdateStatusChangedParams> {
  protected readonly eventName = "app_update.status_changed";

  constructor(
    params: AppUpdateStatusChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
