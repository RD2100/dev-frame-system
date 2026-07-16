import { createI18nRuntime, type I18nRuntime } from "@tutti-os/ui-i18n-runtime";
import { en } from "../locales/en.ts";
import { zhCN } from "../locales/zh-CN.ts";
import type { DesktopLocale } from "./locale.ts";
import type { TranslationDictionary } from "./resources.ts";
import type { DesktopI18nKey, I18nParams } from "./typed.ts";

export interface Translator {
  readonly locale: DesktopLocale;
  t(key: DesktopI18nKey, params?: I18nParams): string;
}

const dictionaries: Record<DesktopLocale, TranslationDictionary> = {
  en,
  "zh-CN": zhCN
};

const runtimes = new Map<DesktopLocale, I18nRuntime<DesktopI18nKey>>();

function createDesktopI18nRuntime(
  locale: DesktopLocale
): I18nRuntime<DesktopI18nKey> {
  return createI18nRuntime<DesktopI18nKey>({
    dictionaries:
      locale === "en"
        ? [dictionaries.en]
        : [dictionaries[locale], dictionaries.en]
  });
}

function getDesktopI18nRuntime(
  locale: DesktopLocale
): I18nRuntime<DesktopI18nKey> {
  const existing = runtimes.get(locale);
  if (existing) {
    return existing;
  }

  const runtime = createDesktopI18nRuntime(locale);
  runtimes.set(locale, runtime);
  return runtime;
}

export function createTranslator(locale: DesktopLocale): Translator {
  const runtime = getDesktopI18nRuntime(locale);

  return {
    locale,
    t(key, params) {
      return runtime.t(key, params);
    }
  };
}
