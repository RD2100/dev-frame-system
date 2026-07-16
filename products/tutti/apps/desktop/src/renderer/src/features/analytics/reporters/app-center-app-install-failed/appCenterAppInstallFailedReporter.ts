import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterAppInstallFailedParams } from "./types.ts";

export class AppCenterAppInstallFailedReporter extends BaseAnalyticsReporter<AppCenterAppInstallFailedParams> {
  protected readonly eventName = "app_center.app_install_failed";

  constructor(
    params: AppCenterAppInstallFailedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
