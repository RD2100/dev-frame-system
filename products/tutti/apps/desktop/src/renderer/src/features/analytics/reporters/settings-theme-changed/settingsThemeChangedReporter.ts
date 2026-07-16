import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { SettingsThemeChangedParams } from "./types.ts";

export class SettingsThemeChangedReporter extends BaseAnalyticsReporter<SettingsThemeChangedParams> {
  protected readonly eventName = "settings.theme_changed";

  constructor(
    params: SettingsThemeChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
