import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterAppUninstalledParams } from "./types.ts";

export class AppCenterAppUninstalledReporter extends BaseAnalyticsReporter<AppCenterAppUninstalledParams> {
  protected readonly eventName = "app_center.app_uninstalled";

  constructor(
    params: AppCenterAppUninstalledParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
