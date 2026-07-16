import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { SettingsWallpaperChangedParams } from "./types.ts";

export class SettingsWallpaperChangedReporter extends BaseAnalyticsReporter<SettingsWallpaperChangedParams> {
  protected readonly eventName = "settings.wallpaper_changed";

  constructor(
    params: SettingsWallpaperChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
