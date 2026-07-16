import type { WorkspaceFileManagerI18nRuntime } from "../../i18n/workspaceFileManagerI18n.ts";
import type { WorkspaceFileManagerHost } from "../workspaceFileManagerHost.interface.ts";
import type { WorkspaceFileManagerHostActionResult } from "../workspaceFileManagerHostTypes.ts";
import type { WorkspaceFileManagerState } from "../workspaceFileManagerTypes.ts";

export interface WorkspaceFileManagerImportControllerInput {
  applyHostActionResult: (
    result: WorkspaceFileManagerHostActionResult | void,
    fallback: { kind: "import" }
  ) => void;
  copy: () => WorkspaceFileManagerI18nRuntime;
  host: WorkspaceFileManagerHost;
  refresh: () => Promise<void>;
  resolveErrorMessage: (error: unknown) => string;
  store: WorkspaceFileManagerState;
}

export class WorkspaceFileManagerImportController {
  private readonly applyHostActionResult: (
    result: WorkspaceFileManagerHostActionResult | void,
    fallback: { kind: "import" }
  ) => void;
  private readonly copy: () => WorkspaceFileManagerI18nRuntime;
  private readonly host: WorkspaceFileManagerHost;
  private readonly refresh: () => Promise<void>;
  private readonly resolveErrorMessage: (error: unknown) => string;
  private readonly store: WorkspaceFileManagerState;

  constructor(input: WorkspaceFileManagerImportControllerInput) {
    this.applyHostActionResult = input.applyHostActionResult;
    this.copy = input.copy;
    this.host = input.host;
    this.refresh = input.refresh;
    this.resolveErrorMessage = input.resolveErrorMessage;
    this.store = input.store;
  }

  async confirmImportConflict(): Promise<void> {
    const importConflictDialog = this.store.importConflictDialog;
    if (!importConflictDialog?.onConfirm) {
      return;
    }

    this.store.busyAction = "import";
    try {
      const result = await importConflictDialog.onConfirm();
      this.store.importConflictDialog = null;
      this.applyHostActionResult(result, { kind: "import" });
    } finally {
      this.store.busyAction = null;
    }
  }

  async importDroppedFiles(
    dataTransfer: Pick<DataTransfer, "files" | "items">,
    targetDirectoryPath: string
  ): Promise<WorkspaceFileManagerHostActionResult> {
    if (!this.host.resolveDroppedPaths || !this.host.importPaths) {
      const result = {
        message: this.copy().t("unsupportedImportBody"),
        supported: false,
        title: this.copy().t("unsupportedImportTitle")
      } as const;
      this.applyHostActionResult(result, { kind: "import" });
      return result;
    }

    const sourcePaths = this.host.resolveDroppedPaths(dataTransfer);
    if (sourcePaths.length === 0) {
      return { supported: true } as const;
    }

    this.store.busyAction = "import";
    try {
      const result = await this.wrapImportAction(
        () =>
          this.host.importPaths?.(
            this.store.workspaceID,
            targetDirectoryPath,
            sourcePaths
          ) ?? Promise.resolve({ supported: true } as const)
      );
      this.applyHostActionResult(result, { kind: "import" });
      return result;
    } finally {
      this.store.busyAction = null;
    }
  }

  async importFiles(
    targetDirectoryPath: string
  ): Promise<WorkspaceFileManagerHostActionResult> {
    if (!this.host.importFiles) {
      const result = {
        message: this.copy().t("unsupportedImportBody"),
        supported: false,
        title: this.copy().t("unsupportedImportTitle")
      } as const;
      this.applyHostActionResult(result, { kind: "import" });
      return result;
    }

    this.store.busyAction = "import";
    try {
      const result = await this.wrapImportAction(
        () =>
          this.host.importFiles?.(
            this.store.workspaceID,
            targetDirectoryPath
          ) ?? Promise.resolve({ supported: true } as const)
      );
      this.applyHostActionResult(result, { kind: "import" });
      return result;
    } finally {
      this.store.busyAction = null;
    }
  }

  private async wrapImportAction(
    action: () => Promise<WorkspaceFileManagerHostActionResult>
  ): Promise<WorkspaceFileManagerHostActionResult> {
    try {
      const result = await action();
      if (result.importConflict) {
        const importConflict = result.importConflict;
        const importConflictConfirm = importConflict.onConfirm;
        return {
          ...result,
          importConflict: {
            ...importConflict,
            onConfirm: importConflictConfirm
              ? async () => {
                  const confirmResult = await importConflictConfirm();
                  await this.refresh();
                  return confirmResult;
                }
              : undefined
          }
        };
      }
      await this.refresh();
      return result;
    } catch (error) {
      return {
        message: this.resolveErrorMessage(error),
        supported: false,
        title: this.copy().t("importFailedTitle")
      };
    }
  }
}
