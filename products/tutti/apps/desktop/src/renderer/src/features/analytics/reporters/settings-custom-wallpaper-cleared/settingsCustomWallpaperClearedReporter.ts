import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { SettingsCustomWallpaperClearedParams } from "./types.ts";

export class SettingsCustomWallpaperClearedReporter extends BaseAnalyticsReporter<SettingsCustomWallpaperClearedParams> {
  protected readonly eventName = "settings.custom_wallpaper_cleared";

  constructor(
    params: SettingsCustomWallpaperClearedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
