import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterOpenedParams } from "./types.ts";

export class AppCenterOpenedReporter extends BaseAnalyticsReporter<AppCenterOpenedParams> {
  protected readonly eventName = "app_center.opened";

  constructor(
    params: AppCenterOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
