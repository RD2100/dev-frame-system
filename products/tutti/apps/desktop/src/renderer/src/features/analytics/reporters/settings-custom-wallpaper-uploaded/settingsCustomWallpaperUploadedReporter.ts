import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { SettingsCustomWallpaperUploadedParams } from "./types.ts";

export class SettingsCustomWallpaperUploadedReporter extends BaseAnalyticsReporter<SettingsCustomWallpaperUploadedParams> {
  protected readonly eventName = "settings.custom_wallpaper_uploaded";

  constructor(
    params: SettingsCustomWallpaperUploadedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
