import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterAppDeletedParams } from "./types.ts";

export class AppCenterAppDeletedReporter extends BaseAnalyticsReporter<AppCenterAppDeletedParams> {
  protected readonly eventName = "app_center.app_deleted";

  constructor(
    params: AppCenterAppDeletedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
