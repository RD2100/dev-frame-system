import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterAppInstalledParams } from "./types.ts";

export class AppCenterAppInstalledReporter extends BaseAnalyticsReporter<AppCenterAppInstalledParams> {
  protected readonly eventName = "app_center.app_installed";

  constructor(
    params: AppCenterAppInstalledParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
