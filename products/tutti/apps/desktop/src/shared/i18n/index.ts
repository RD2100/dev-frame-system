export {
  defaultDesktopLocale,
  desktopLocales,
  isDesktopLocale,
  normalizeDesktopLocale,
  resolveDesktopLocaleFromCandidates,
  toDocumentLanguage,
  type DesktopLocale
} from "./core/locale.ts";
export { createTranslator, type Translator } from "./core/translate.ts";
export type { TranslationDictionary } from "./core/resources.ts";
export type { DesktopI18nKey, I18nParams } from "./core/typed.ts";
export { en } from "./locales/en.ts";
export { zhCN } from "./locales/zh-CN.ts";
export {
  createDesktopErrorI18nRuntime,
  desktopErrorI18nResources
} from "./desktopErrorI18n.ts";
export {
  createWorkspaceWorkbenchDesktopI18nRuntime,
  workspaceWorkbenchDesktopI18nKeys,
  workspaceWorkbenchDesktopI18nNamespace,
  workspaceWorkbenchDesktopI18nResources,
  type WorkspaceWorkbenchDesktopI18nKey,
  type WorkspaceWorkbenchDesktopI18nRuntime
} from "./workspaceWorkbenchDesktopI18n.ts";
