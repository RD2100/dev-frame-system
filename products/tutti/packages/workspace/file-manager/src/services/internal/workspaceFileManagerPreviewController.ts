import type { WorkspaceFilePreviewReadonlyReason } from "@tutti-os/workspace-file-preview";
import {
  createWorkspaceFilePreviewLoadedState,
  formatWorkspacePreviewByteLimit,
  normalizeWorkspaceFilePreviewBytes,
  resolveWorkspaceFilePreviewReadiness,
  workspaceFilePreviewMaxBytes
} from "../workspaceFileManagerModel.ts";
import type { WorkspaceFileManagerI18nRuntime } from "../../i18n/workspaceFileManagerI18n.ts";
import type { WorkspaceFileManagerHost } from "../workspaceFileManagerHost.interface.ts";
import type { WorkspaceFileManagerState } from "../workspaceFileManagerTypes.ts";
import { findWorkspaceFileEntry } from "./model/entryLookup.ts";

export interface WorkspaceFileManagerPreviewControllerInput {
  copy: () => WorkspaceFileManagerI18nRuntime;
  host: WorkspaceFileManagerHost;
  isDisposed: () => boolean;
  resolveErrorMessage: (
    error: unknown,
    overrides?: Record<string, string | undefined>
  ) => string;
  store: WorkspaceFileManagerState;
}

export class WorkspaceFileManagerPreviewController {
  private readonly copy: () => WorkspaceFileManagerI18nRuntime;
  private readonly host: WorkspaceFileManagerHost;
  private readonly isDisposed: () => boolean;
  private readonly resolveErrorMessage: (
    error: unknown,
    overrides?: Record<string, string | undefined>
  ) => string;
  private readonly store: WorkspaceFileManagerState;
  private previewObjectUrl: string | null = null;
  private previewRequestSeq = 0;

  constructor(input: WorkspaceFileManagerPreviewControllerInput) {
    this.copy = input.copy;
    this.host = input.host;
    this.isDisposed = input.isDisposed;
    this.resolveErrorMessage = input.resolveErrorMessage;
    this.store = input.store;
  }

  dispose(): void {
    this.previewRequestSeq += 1;
    this.revokePreviewObjectUrl();
  }

  async syncPreviewState(): Promise<void> {
    const requestID = this.previewRequestSeq + 1;
    this.previewRequestSeq = requestID;
    this.revokePreviewObjectUrl();

    const selectedEntry = findWorkspaceFileEntry(
      this.store,
      this.store.selectedPath
    );
    const copy = this.copy();

    if (!selectedEntry) {
      this.store.previewState = { status: "empty" };
      return;
    }

    const readiness = resolveWorkspaceFilePreviewReadiness(selectedEntry);
    if (readiness.status === "directory") {
      this.store.previewState = {
        entry: selectedEntry,
        status: "directory"
      };
      return;
    }
    if (readiness.status === "unsupported") {
      this.store.previewState = {
        entry: selectedEntry,
        message: copy.t("previewUnsupported"),
        status: "unsupported"
      };
      return;
    }
    if (readiness.status === "readonly") {
      this.store.previewState = {
        entry: selectedEntry,
        message: resolveWorkspaceFileManagerPreviewReadonlyMessage(
          copy,
          readiness.reason,
          readiness.maxSizeBytes
        ),
        status: "readonly"
      };
      return;
    }

    const activationTarget = readiness.target;

    this.store.previewState = {
      entry: activationTarget,
      status: "loading"
    };

    if (!this.host.readPreviewFile) {
      this.store.previewState = {
        entry: selectedEntry,
        message: copy.t("previewUnsupported"),
        status: "unsupported"
      };
      return;
    }

    try {
      const bytes = normalizeWorkspaceFilePreviewBytes(
        await this.host.readPreviewFile(
          this.store.workspaceID,
          selectedEntry.path
        )
      );
      if (this.isDisposed() || requestID !== this.previewRequestSeq) {
        return;
      }

      const loadedState = createWorkspaceFilePreviewLoadedState({
        bytes,
        entry: selectedEntry,
        renderHtml: true,
        target: activationTarget
      });
      if (loadedState.status === "image" || loadedState.status === "video") {
        const objectUrl = URL.createObjectURL(
          new Blob([loadedState.bytes], {
            type: loadedState.contentType
          })
        );
        if (this.isDisposed() || requestID !== this.previewRequestSeq) {
          URL.revokeObjectURL(objectUrl);
          return;
        }

        this.previewObjectUrl = objectUrl;
        this.store.previewState = {
          entry: activationTarget,
          objectUrl,
          status: loadedState.status
        };
        return;
      }

      if (loadedState.status === "text") {
        this.store.previewState = loadedState;
        return;
      }

      if (loadedState.status === "html") {
        this.store.previewState = loadedState;
        return;
      }

      if (loadedState.status === "readonly") {
        this.store.previewState = {
          entry: selectedEntry,
          message: resolveWorkspaceFileManagerPreviewReadonlyMessage(
            copy,
            loadedState.reason,
            loadedState.maxSizeBytes
          ),
          status: "readonly"
        };
      }
    } catch (error) {
      if (this.isDisposed() || requestID !== this.previewRequestSeq) {
        return;
      }

      this.store.previewState = {
        entry: selectedEntry,
        message: this.resolveErrorMessage(error, {
          preview_file_too_large: copy.t("previewFileTooLarge", {
            maxSize: formatWorkspacePreviewByteLimit(
              workspaceFilePreviewMaxBytes
            )
          })
        }),
        status: "error"
      };
    }
  }

  private revokePreviewObjectUrl(): void {
    if (!this.previewObjectUrl) {
      return;
    }
    URL.revokeObjectURL(this.previewObjectUrl);
    this.previewObjectUrl = null;
  }
}

function resolveWorkspaceFileManagerPreviewReadonlyMessage(
  copy: WorkspaceFileManagerI18nRuntime,
  reason: WorkspaceFilePreviewReadonlyReason,
  maxSizeBytes?: number
): string {
  switch (reason) {
    case "binary":
      return copy.t("previewBinary");
    case "decode_failed":
      return copy.t("previewDecodeFailed");
    case "file_too_large":
      return copy.t("previewFileTooLarge", {
        maxSize: formatWorkspacePreviewByteLimit(maxSizeBytes ?? 0)
      });
    case "text_too_large":
      return copy.t("previewTooLarge", {
        maxSize: formatWorkspacePreviewByteLimit(maxSizeBytes ?? 0)
      });
  }
}
