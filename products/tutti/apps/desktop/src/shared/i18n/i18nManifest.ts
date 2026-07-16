import { createLocaleObjectI18nModuleManifest } from "@tutti-os/ui-i18n-runtime";

export const tuttiI18nModule = createLocaleObjectI18nModuleManifest({
  fileByLocale: {
    en: "apps/desktop/src/shared/i18n/locales/en.ts",
    "zh-CN": "apps/desktop/src/shared/i18n/locales/zh-CN.ts"
  },
  name: "desktop-locales"
});
