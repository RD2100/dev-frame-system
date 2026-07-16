import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterAppStoppedParams } from "./types.ts";

export class AppCenterAppStoppedReporter extends BaseAnalyticsReporter<AppCenterAppStoppedParams> {
  protected readonly eventName = "app_center.app_stopped";

  constructor(
    params: AppCenterAppStoppedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
