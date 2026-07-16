import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterAppOpenedParams } from "./types.ts";

export class AppCenterAppOpenedReporter extends BaseAnalyticsReporter<AppCenterAppOpenedParams> {
  protected readonly eventName = "app_center.app_opened";

  constructor(
    params: AppCenterAppOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
