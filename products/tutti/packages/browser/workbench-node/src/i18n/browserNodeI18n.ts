import {
  createI18nRuntime,
  createScopedI18nRuntime,
  createScopedLocaleObjectsI18nModuleManifest,
  type I18nDictionary,
  type I18nRuntime
} from "@tutti-os/ui-i18n-runtime";

type BrowserNodeI18nLocale = "en" | "zh-CN";
export const browserNodeI18nNamespace = "browserNode";
export const browserNodeI18nModule =
  createScopedLocaleObjectsI18nModuleManifest({
    localeObjectByLocale: {
      en: "browserNodeEn",
      "zh-CN": "browserNodeZhCN"
    },
    name: "browser-node",
    namespace: "browserNode",
    sourceRoot: "packages/browser/workbench-node/src"
  });

const browserNodeEn = {
  actions: {
    back: "Back",
    forward: "Forward",
    openDevTools: "Open DevTools",
    openExternal: "Open in external browser",
    reload: "Reload"
  },
  addressLabel: "Address",
  addressPlaceholder: "Search or enter address",
  coldStatus: "Sleeping",
  dockLabel: "Browser",
  errors: {
    invalidUrl: "Enter a valid web address.",
    navigationFailed: "The page could not be loaded.",
    navigationFailedWithStatus:
      "The page could not be loaded. HTTP {{statusCode}}.",
    errorCode: "Error {{errorCode}}",
    statusCode: "HTTP {{statusCode}}",
    unsupportedProtocol: "This address type is not supported.",
    unsupportedUrl: "This page cannot be opened."
  },
  loadFailed: "Page load failed",
  title: "Browser"
} as const satisfies I18nDictionary;

const browserNodeZhCN = {
  actions: {
    back: "后退",
    forward: "前进",
    openDevTools: "打开开发者工具",
    openExternal: "使用外部浏览器打开",
    reload: "重新加载"
  },
  addressLabel: "地址",
  addressPlaceholder: "搜索或输入地址",
  coldStatus: "休眠中",
  dockLabel: "浏览器",
  errors: {
    invalidUrl: "请输入有效的网址。",
    navigationFailed: "页面无法加载。",
    navigationFailedWithStatus: "页面无法加载。HTTP {{statusCode}}。",
    errorCode: "错误 {{errorCode}}",
    statusCode: "HTTP {{statusCode}}",
    unsupportedProtocol: "不支持此地址类型。",
    unsupportedUrl: "无法打开此页面。"
  },
  loadFailed: "页面加载失败",
  title: "浏览器"
} as const satisfies I18nDictionary;

export type BrowserNodeI18nKey =
  | "actions.back"
  | "actions.forward"
  | "actions.openDevTools"
  | "actions.openExternal"
  | "actions.reload"
  | "addressLabel"
  | "addressPlaceholder"
  | "coldStatus"
  | "dockLabel"
  | "errors.invalidUrl"
  | "errors.errorCode"
  | "errors.navigationFailed"
  | "errors.navigationFailedWithStatus"
  | "errors.statusCode"
  | "errors.unsupportedProtocol"
  | "errors.unsupportedUrl"
  | "loadFailed"
  | "title";

export type BrowserNodeI18nRuntime = I18nRuntime<BrowserNodeI18nKey>;

const browserNodeDefaults: Record<BrowserNodeI18nLocale, I18nDictionary> = {
  en: browserNodeEn,
  "zh-CN": browserNodeZhCN
};

export const browserNodeI18nResources = {
  en: {
    [browserNodeI18nNamespace]: browserNodeDefaults.en
  },
  "zh-CN": {
    [browserNodeI18nNamespace]: browserNodeDefaults["zh-CN"]
  }
} as const satisfies Record<BrowserNodeI18nLocale, I18nDictionary>;

const defaultBrowserNodeI18n = createI18nRuntime({
  dictionaries: [browserNodeI18nResources.en]
});

export function createBrowserNodeI18nRuntime(
  runtime: I18nRuntime<string> | undefined
): BrowserNodeI18nRuntime {
  return createScopedI18nRuntime<BrowserNodeI18nKey>(
    runtime ?? defaultBrowserNodeI18n,
    browserNodeI18nNamespace
  );
}
