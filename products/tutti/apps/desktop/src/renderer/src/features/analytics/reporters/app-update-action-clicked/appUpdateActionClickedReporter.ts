import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppUpdateActionClickedParams } from "./types.ts";

export class AppUpdateActionClickedReporter extends BaseAnalyticsReporter<AppUpdateActionClickedParams> {
  protected readonly eventName = "app_update.action_clicked";

  constructor(
    params: AppUpdateActionClickedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
