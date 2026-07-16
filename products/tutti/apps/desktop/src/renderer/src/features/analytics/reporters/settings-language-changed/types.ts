import type { DesktopLocale } from "@shared/i18n";
import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface SettingsLanguageChangedParams extends AnalyticsReporterParams {
  fromLanguage: DesktopLocale;
  toLanguage: DesktopLocale;
}
