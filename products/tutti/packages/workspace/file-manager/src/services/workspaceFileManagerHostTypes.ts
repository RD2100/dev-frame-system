import type {
  WorkspaceFileActivationTarget,
  WorkspaceFileEntry,
  WorkspaceFileImportSummary,
  WorkspaceFileImportConflict
} from "./workspaceFileManagerTypes.ts";

export type WorkspaceFileManagerHostActionMessageStatus =
  | "cancelled"
  | "completed"
  | "started";

export interface WorkspaceFileManagerHostActionMessage {
  actionKind: "export" | "import";
  entry?: WorkspaceFileEntry | null;
  message: string;
  status: WorkspaceFileManagerHostActionMessageStatus;
}

export interface WorkspaceFileManagerHostImportResult {
  cancelledMessage?: string | null;
  completedMessage?: string | null;
  startedMessage?: string | null;
  summary?: WorkspaceFileImportSummary | null;
  message?: string | null;
  supported: boolean;
  title?: string | null;
  importConflict?: WorkspaceFileManagerHostImportConflict | null;
}

export interface WorkspaceFileManagerHostExportResult {
  cancelledMessage?: string | null;
  completedMessage?: string | null;
  message?: string | null;
  startedMessage?: string | null;
  supported: boolean;
  title?: string | null;
  importConflict?: null;
}

export type WorkspaceFileManagerHostActionResult =
  | WorkspaceFileManagerHostExportResult
  | WorkspaceFileManagerHostImportResult;

export interface WorkspaceFileManagerHostImportConflict {
  conflicts: WorkspaceFileImportConflict[];
  summary?: WorkspaceFileImportSummary | null;
  onConfirm?: () => Promise<WorkspaceFileManagerHostImportResult | void>;
}

export interface WorkspaceFileManagerFileActivationRequest {
  entry: WorkspaceFileEntry;
  target: WorkspaceFileActivationTarget | null;
}

export type WorkspaceFileManagerHostFallbackActionKind =
  | "download"
  | "none"
  | "open";

export type WorkspaceFileManagerHostFallbackAction =
  | {
      kind: "download" | "open";
      label?: string | null;
      onSelect: () => Promise<WorkspaceFileManagerHostFileActivationResult | void>;
    }
  | {
      kind: "none";
      label?: string | null;
    };

export type WorkspaceFileManagerHostFileActivationResult =
  | {
      disposition: "handled";
    }
  | {
      actions?: WorkspaceFileManagerHostFallbackAction[] | null;
      disposition: "fallback" | "unsupported";
      message?: string | null;
      title?: string | null;
    };
