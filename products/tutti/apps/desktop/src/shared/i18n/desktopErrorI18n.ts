import {
  createI18nRuntime,
  type I18nDictionary,
  type I18nRuntime
} from "@tutti-os/ui-i18n-runtime";
import type { DesktopLocale } from "./core/locale.ts";
import { en } from "./locales/en.ts";
import { zhCN } from "./locales/zh-CN.ts";

export const desktopErrorI18nResources: Record<DesktopLocale, I18nDictionary> =
  {
    en: {
      common: {
        unknownError: en.common.unknownError
      },
      errors: en.errors
    },
    "zh-CN": {
      common: {
        unknownError: zhCN.common.unknownError
      },
      errors: zhCN.errors
    }
  };

const desktopErrorI18nRuntimes: Record<DesktopLocale, I18nRuntime<string>> = {
  en: createI18nRuntime({
    dictionaries: [desktopErrorI18nResources.en]
  }),
  "zh-CN": createI18nRuntime({
    dictionaries: [desktopErrorI18nResources["zh-CN"]]
  })
};

export function createDesktopErrorI18nRuntime(
  locale: DesktopLocale
): I18nRuntime<string> {
  return desktopErrorI18nRuntimes[locale];
}
