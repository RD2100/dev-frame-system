import type { I18nRuntime } from "@tutti-os/ui-i18n-runtime";
import {
  createTerminalNodeI18nRuntime,
  type TerminalNodeI18nRuntime
} from "../i18n/terminalNodeI18n.ts";
import type {
  TerminalCloseGuardService,
  TerminalDiagnostics,
  TerminalDropInputResolver,
  TerminalLaunchService,
  TerminalLinkHandler,
  TerminalNodeLimits,
  TerminalOutputTransform,
  TerminalThemeResolver,
  TerminalTransport
} from "../contracts/index.ts";

export interface TerminalNodeFeature {
  closeGuard: TerminalCloseGuardService;
  diagnostics: TerminalDiagnostics;
  dropInput?: TerminalDropInputResolver;
  i18n: TerminalNodeI18nRuntime;
  launchService: TerminalLaunchService;
  limits: TerminalNodeLimits;
  linkHandler?: TerminalLinkHandler;
  outputTransform?: TerminalOutputTransform;
  resolveTheme: TerminalThemeResolver;
  transport: TerminalTransport;
}

export interface CreateTerminalNodeFeatureInput {
  closeGuard: TerminalCloseGuardService;
  diagnostics?: TerminalDiagnostics;
  dropInput?: TerminalDropInputResolver;
  i18n?: I18nRuntime<string>;
  launchService: TerminalLaunchService;
  limits?: Partial<TerminalNodeLimits>;
  linkHandler?: TerminalLinkHandler;
  outputTransform?: TerminalOutputTransform;
  resolveTheme?: TerminalThemeResolver;
  transport: TerminalTransport;
}

export const defaultTerminalNodeLimits: TerminalNodeLimits = {
  maxScrollbackLines: 10_000,
  maxWriteBatchBytes: 64 * 1024,
  snapshotChunkBytes: 256 * 1024
};

const noopTerminalDiagnostics: TerminalDiagnostics = {
  log() {
    return undefined;
  }
};

const defaultResolveTerminalTheme: TerminalThemeResolver = () => ({});

export function createTerminalNodeFeature(
  input: CreateTerminalNodeFeatureInput
): TerminalNodeFeature {
  return {
    closeGuard: input.closeGuard,
    diagnostics: input.diagnostics ?? noopTerminalDiagnostics,
    dropInput: input.dropInput,
    i18n: createTerminalNodeI18nRuntime(input.i18n),
    launchService: input.launchService,
    limits: {
      ...defaultTerminalNodeLimits,
      ...input.limits
    },
    linkHandler: input.linkHandler,
    outputTransform: input.outputTransform,
    resolveTheme: input.resolveTheme ?? defaultResolveTerminalTheme,
    transport: input.transport
  };
}
