import type {
  WorkbenchHostCloseDialogRequest,
  WorkbenchHostCloseEffect
} from "@tutti-os/workbench-surface";
import type { TerminalCloseGuardResult } from "@tutti-os/workspace-terminal/contracts";
import {
  workspaceWorkbenchDesktopI18nKeys,
  type WorkspaceWorkbenchDesktopI18nRuntime
} from "../../../../../../shared/i18n/index.ts";

export function createTerminalCloseDialogRequest(input: {
  guard: TerminalCloseGuardResult;
  i18n: WorkspaceWorkbenchDesktopI18nRuntime;
}): WorkbenchHostCloseDialogRequest {
  return {
    cancelLabel: input.i18n.t(
      workspaceWorkbenchDesktopI18nKeys.closeGuard.cancel
    ),
    confirmLabel: input.i18n.t(
      workspaceWorkbenchDesktopI18nKeys.closeGuard.confirm
    ),
    description: input.i18n.t(
      workspaceWorkbenchDesktopI18nKeys.closeGuard.description
    ),
    details: input.guard.leaderCommand ?? null,
    scope: "node",
    title: input.i18n.t(workspaceWorkbenchDesktopI18nKeys.closeGuard.title),
    variant: "destructive"
  };
}

export function createWindowCloseDialogRequest(input: {
  effects: readonly WorkbenchHostCloseEffect[];
  i18n: WorkspaceWorkbenchDesktopI18nRuntime;
}): WorkbenchHostCloseDialogRequest | null {
  if (input.effects.length === 0) {
    return null;
  }

  return {
    cancelLabel: input.i18n.t(
      workspaceWorkbenchDesktopI18nKeys.windowCloseGuard.cancel
    ),
    confirmLabel: input.i18n.t(
      workspaceWorkbenchDesktopI18nKeys.windowCloseGuard.confirm
    ),
    description: input.i18n.t(
      workspaceWorkbenchDesktopI18nKeys.windowCloseGuard.description
    ),
    details: input.effects
      .map((effect) =>
        effect.description
          ? `${effect.title}\n${effect.description}`
          : effect.title
      )
      .join("\n\n"),
    scope: "window",
    title: input.i18n.t(
      workspaceWorkbenchDesktopI18nKeys.windowCloseGuard.title
    ),
    variant: "destructive"
  };
}
