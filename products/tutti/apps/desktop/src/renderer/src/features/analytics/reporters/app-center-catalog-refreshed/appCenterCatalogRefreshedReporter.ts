import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppCenterCatalogRefreshedParams } from "./types.ts";

export class AppCenterCatalogRefreshedReporter extends BaseAnalyticsReporter<AppCenterCatalogRefreshedParams> {
  protected readonly eventName = "app_center.catalog_refreshed";

  constructor(
    params: AppCenterCatalogRefreshedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
