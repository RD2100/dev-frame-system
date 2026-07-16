import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { SettingsOpenedParams } from "./types.ts";

export class SettingsOpenedReporter extends BaseAnalyticsReporter<SettingsOpenedParams> {
  protected readonly eventName = "settings.opened";

  constructor(
    params: SettingsOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
