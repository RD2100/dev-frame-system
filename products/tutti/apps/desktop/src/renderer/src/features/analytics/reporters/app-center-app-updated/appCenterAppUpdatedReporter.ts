import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterAppUpdatedParams } from "./types.ts";

export class AppCenterAppUpdatedReporter extends BaseAnalyticsReporter<AppCenterAppUpdatedParams> {
  protected readonly eventName = "app_center.app_updated";

  constructor(
    params: AppCenterAppUpdatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
