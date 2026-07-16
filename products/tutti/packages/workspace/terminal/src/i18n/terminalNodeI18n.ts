import {
  createI18nRuntime,
  createScopedI18nRuntime,
  createScopedLocaleObjectsI18nModuleManifest,
  type I18nDictionary,
  type I18nRuntime
} from "@tutti-os/ui-i18n-runtime";

type TerminalNodeI18nLocale = "en" | "zh-CN";

export const terminalNodeI18nNamespace = "terminalNode";
export const terminalNodeI18nModule =
  createScopedLocaleObjectsI18nModuleManifest({
    localeObjectByLocale: {
      en: "terminalNodeEn",
      "zh-CN": "terminalNodeZhCN"
    },
    name: "workspace-terminal",
    namespace: terminalNodeI18nNamespace,
    sourceRoot: "packages/workspace/terminal/src"
  });

const terminalNodeEn = {
  actions: {
    caseSensitive: "Case sensitive",
    close: "Close terminal",
    find: "Find",
    next: "Next match",
    previous: "Previous match",
    regex: "Regular expression"
  },
  closeGuard: {
    cancel: "Keep running",
    confirm: "Terminate",
    description:
      "This terminal still has running work. Terminating it will stop the session.",
    title: "Terminate terminal?"
  },
  dockLabel: "Terminal",
  emptySession: "No terminal session",
  findPlaceholder: "Search terminal",
  recovery: {
    replayGap:
      "Terminal output recovery skipped some history. New output will continue from the live session.",
    snapshotTruncated:
      "Terminal recovery snapshot was truncated. Earlier output is no longer available."
  },
  status: {
    created: "Created",
    detached: "Detached",
    exited: "Exited",
    failed: "Failed",
    running: "Running",
    starting: "Starting"
  },
  title: "Terminal"
} as const satisfies I18nDictionary;

const terminalNodeZhCN = {
  actions: {
    caseSensitive: "区分大小写",
    close: "关闭终端",
    find: "查找",
    next: "下一个匹配项",
    previous: "上一个匹配项",
    regex: "正则表达式"
  },
  closeGuard: {
    cancel: "继续运行",
    confirm: "终止",
    description: "这个终端仍有任务在运行。终止会停止当前终端会话。",
    title: "终止终端？"
  },
  dockLabel: "终端",
  emptySession: "没有终端会话",
  findPlaceholder: "搜索终端",
  recovery: {
    replayGap: "终端恢复时跳过了一部分历史输出。新的输出会继续从当前会话接收。",
    snapshotTruncated: "终端恢复快照已被截断，更早的输出已经不可用。"
  },
  status: {
    created: "已创建",
    detached: "已断开",
    exited: "已退出",
    failed: "失败",
    running: "运行中",
    starting: "启动中"
  },
  title: "终端"
} as const satisfies I18nDictionary;

export type TerminalNodeI18nKey =
  | "actions.caseSensitive"
  | "actions.close"
  | "actions.find"
  | "actions.next"
  | "actions.previous"
  | "actions.regex"
  | "closeGuard.cancel"
  | "closeGuard.confirm"
  | "closeGuard.description"
  | "closeGuard.title"
  | "dockLabel"
  | "emptySession"
  | "findPlaceholder"
  | "recovery.replayGap"
  | "recovery.snapshotTruncated"
  | "status.created"
  | "status.detached"
  | "status.exited"
  | "status.failed"
  | "status.running"
  | "status.starting"
  | "title";

export type TerminalNodeI18nRuntime = I18nRuntime<TerminalNodeI18nKey>;

const terminalNodeDefaults: Record<TerminalNodeI18nLocale, I18nDictionary> = {
  en: terminalNodeEn,
  "zh-CN": terminalNodeZhCN
};

export const terminalNodeI18nResources = {
  en: {
    [terminalNodeI18nNamespace]: terminalNodeDefaults.en
  },
  "zh-CN": {
    [terminalNodeI18nNamespace]: terminalNodeDefaults["zh-CN"]
  }
} as const satisfies Record<TerminalNodeI18nLocale, I18nDictionary>;

const defaultTerminalNodeI18n = createI18nRuntime({
  dictionaries: [terminalNodeI18nResources.en]
});

export function createTerminalNodeI18nRuntime(
  runtime: I18nRuntime<string> | undefined
): TerminalNodeI18nRuntime {
  return createScopedI18nRuntime<TerminalNodeI18nKey>(
    runtime ?? defaultTerminalNodeI18n,
    terminalNodeI18nNamespace
  );
}
