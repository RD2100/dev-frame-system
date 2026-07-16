import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterFactoryJobCreatedParams } from "./types.ts";

export class AppCenterFactoryJobCreatedReporter extends BaseAnalyticsReporter<AppCenterFactoryJobCreatedParams> {
  protected readonly eventName = "app_center.factory_job_created";

  constructor(
    params: AppCenterFactoryJobCreatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
