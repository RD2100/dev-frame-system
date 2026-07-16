import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { SettingsSectionSwitchedParams } from "./types.ts";

export class SettingsSectionSwitchedReporter extends BaseAnalyticsReporter<SettingsSectionSwitchedParams> {
  protected readonly eventName = "settings.section_switched";

  constructor(
    params: SettingsSectionSwitchedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
