import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { SettingsLanguageChangedParams } from "./types.ts";

export class SettingsLanguageChangedReporter extends BaseAnalyticsReporter<SettingsLanguageChangedParams> {
  protected readonly eventName = "settings.language_changed";

  constructor(
    params: SettingsLanguageChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
