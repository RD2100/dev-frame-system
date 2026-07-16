import {
  Button,
  ConfirmationDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input
} from "@tutti-os/ui-system";
import type { ReactElement } from "react";
import type {
  WorkspaceFileManagerI18nKey,
  WorkspaceFileManagerI18nRuntime
} from "../i18n/workspaceFileManagerI18n.ts";
import type {
  WorkspaceFileEntry,
  WorkspaceFileImportSummaryReason
} from "../services/workspaceFileManagerTypes.ts";
import type {
  WorkspaceFileManagerHostFallbackAction,
  WorkspaceFileManagerHostImportConflict
} from "./workspaceFileManagerHostTypes.ts";

export function WorkspaceFileManagerCreateDialog({
  busy,
  copy,
  dialog,
  onClose,
  onConfirm,
  onNameChange
}: {
  busy: boolean;
  copy: WorkspaceFileManagerI18nRuntime;
  dialog: {
    errorMessage: string | null;
    kind: "directory" | "file";
    name: string;
  } | null;
  onClose: () => void;
  onConfirm: () => void;
  onNameChange: (name: string) => void;
}): ReactElement | null {
  if (!dialog) {
    return null;
  }

  return (
    <Dialog
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose();
        }
      }}
    >
      <DialogContent aria-busy={busy} showCloseButton={false}>
        <form
          className="grid gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            onConfirm();
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {dialog.kind === "directory"
                ? copy.t("createDirectoryLabel")
                : copy.t("createFileLabel")}
            </DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder={
              dialog.kind === "directory"
                ? copy.t("createDirectoryPlaceholder")
                : copy.t("createFilePlaceholder")
            }
            value={dialog.name}
            onChange={(event) => {
              onNameChange(event.currentTarget.value);
            }}
          />
          {dialog.errorMessage ? (
            <p className="text-[13px] text-[var(--state-danger)]">
              {dialog.errorMessage}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              disabled={busy}
              size="dialog"
              type="button"
              variant="ghost"
              onClick={onClose}
            >
              {copy.t("cancelLabel")}
            </Button>
            <Button disabled={busy} size="dialog" type="submit">
              {copy.t("createActionLabel")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function WorkspaceFileManagerDeleteDialog({
  busy,
  copy,
  entry,
  onClose,
  onConfirm
}: {
  busy: boolean;
  copy: WorkspaceFileManagerI18nRuntime;
  entry: WorkspaceFileEntry | null;
  onClose: () => void;
  onConfirm: () => void;
}): ReactElement | null {
  if (!entry) {
    return null;
  }

  return (
    <ConfirmationDialog
      cancelLabel={copy.t("cancelLabel")}
      confirmBusy={busy}
      confirmLabel={busy ? copy.t("deletingLabel") : copy.t("deleteLabel")}
      description={copy.t("deleteConfirmDescription", { name: entry.name })}
      open
      title={copy.t("deleteLabel")}
      tone="destructive"
      onConfirm={onConfirm}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose();
        }
      }}
    />
  );
}

export function WorkspaceFileManagerUnsupportedDialog({
  copy,
  dialog,
  isViewing,
  onAction,
  onClose
}: {
  copy: WorkspaceFileManagerI18nRuntime;
  dialog: {
    actions?: WorkspaceFileManagerHostFallbackAction[] | null;
    kind: "import" | "view";
    message?: string | null;
    title?: string | null;
    entry?: WorkspaceFileEntry;
  } | null;
  isViewing: boolean;
  onAction: (action: WorkspaceFileManagerHostFallbackAction) => void;
  onClose: () => void;
}): ReactElement | null {
  if (!dialog) {
    return null;
  }

  const title =
    dialog.title ??
    (dialog.kind === "import"
      ? copy.t("unsupportedImportTitle")
      : copy.t("unsupportedViewTitle"));
  const body =
    dialog.message ??
    (dialog.kind === "import"
      ? copy.t("unsupportedImportBody")
      : copy.t("unsupportedViewBody", { name: dialog.entry?.name ?? "" }));
  const actions =
    dialog.actions?.filter((action) => action.kind !== "none") ?? [];

  return (
    <Dialog
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose();
        }
      }}
    >
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={(event) => {
          if (isViewing) {
            event.preventDefault();
          }
        }}
        onInteractOutside={(event) => {
          if (isViewing) {
            event.preventDefault();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{body}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            disabled={isViewing}
            size="dialog"
            type="button"
            variant="ghost"
            onClick={onClose}
          >
            {copy.t("closeLabel")}
          </Button>
          {actions.map((action) => (
            <Button
              key={action.kind}
              disabled={isViewing}
              size="dialog"
              type="button"
              className="shadow-none"
              onClick={() => {
                onAction(action);
              }}
            >
              {action.label ??
                (action.kind === "download"
                  ? copy.t("downloadLabel")
                  : copy.t("openLabel"))}
            </Button>
          ))}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function WorkspaceFileManagerImportConflictDialog({
  busy,
  copy,
  dialog,
  onClose,
  onConfirm
}: {
  busy: boolean;
  copy: WorkspaceFileManagerI18nRuntime;
  dialog: WorkspaceFileManagerHostImportConflict | null;
  onClose: () => void;
  onConfirm: () => void;
}): ReactElement | null {
  if (!dialog) {
    return null;
  }

  const hasBlockedConflict = dialog.conflicts.some(
    (conflict) => conflict.conflictKind === "type_mismatch"
  );

  return (
    <ConfirmationDialog
      cancelLabel={
        hasBlockedConflict ? copy.t("closeLabel") : copy.t("cancelLabel")
      }
      className="max-w-lg"
      confirmBusy={busy}
      confirmLabel={
        hasBlockedConflict
          ? copy.t("closeLabel")
          : copy.t("importConflictReplaceLabel")
      }
      description={
        hasBlockedConflict
          ? copy.t("importTypeConflictDescription", {
              count: dialog.conflicts.length
            })
          : copy.t("importConflictDescription", {
              count: dialog.conflicts.length
            })
      }
      hideConfirmButton={hasBlockedConflict}
      open
      title={
        hasBlockedConflict
          ? copy.t("importTypeConflictTitle")
          : copy.t("importConflictTitle")
      }
      tone={hasBlockedConflict ? "default" : "destructive"}
      onConfirm={hasBlockedConflict ? onClose : onConfirm}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose();
        }
      }}
    >
      <ImportConflictSummary copy={copy} dialog={dialog} />
      <div className="max-h-60 overflow-auto rounded-lg border border-[var(--border-1)] bg-transparency-block">
        <div className="divide-y divide-[var(--border-1)]">
          {dialog.conflicts.map((conflict) => (
            <div
              key={`${conflict.destinationPath}:${conflict.sourcePath}`}
              className="flex flex-col gap-1 px-4 py-3 text-[13px]"
            >
              <span className="font-medium text-[var(--text-primary)]">
                {conflict.name}
              </span>
              <span className="text-[11px] text-[var(--text-secondary)]">
                {copy.t("importConflictReviewLabel")}:{" "}
                {conflict.destinationPath}
              </span>
            </div>
          ))}
        </div>
      </div>
    </ConfirmationDialog>
  );
}

function ImportConflictSummary({
  copy,
  dialog
}: {
  copy: WorkspaceFileManagerI18nRuntime;
  dialog: WorkspaceFileManagerHostImportConflict;
}): ReactElement | null {
  const summaryItems: string[] = [];
  const hasReasonBreakdown =
    dialog.summary?.reasonBreakdown?.some((reason) => reason.count > 0) ??
    false;
  if (
    typeof dialog.summary?.selectedCount === "number" &&
    dialog.summary.selectedCount > 0
  ) {
    summaryItems.push(
      copy.t("importConflictSummarySelected", {
        count: dialog.summary.selectedCount
      })
    );
  }
  if (
    !hasReasonBreakdown &&
    typeof dialog.summary?.filteredCount === "number" &&
    dialog.summary.filteredCount > 0
  ) {
    summaryItems.push(
      copy.t("importConflictSummaryFiltered", {
        count: dialog.summary.filteredCount
      })
    );
  }
  if (
    !hasReasonBreakdown &&
    typeof dialog.summary?.ignoredCount === "number" &&
    dialog.summary.ignoredCount > 0
  ) {
    summaryItems.push(
      copy.t("importConflictSummaryIgnored", {
        count: dialog.summary.ignoredCount
      })
    );
  }
  for (const reason of dialog.summary?.reasonBreakdown ?? []) {
    if (reason.count <= 0) {
      continue;
    }
    const copyKey = importSummaryReasonCopyKey(reason.reason);
    if (!copyKey) {
      continue;
    }
    summaryItems.push(copy.t(copyKey, { count: reason.count }));
  }

  if (summaryItems.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
      {summaryItems.map((item) => (
        <span
          key={item}
          className="rounded-md border border-[var(--border-1)] px-2 py-1"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function importSummaryReasonCopyKey(
  reason: WorkspaceFileImportSummaryReason
): WorkspaceFileManagerI18nKey | null {
  switch (reason) {
    case "ignored":
      return "importConflictSummaryReasonIgnored";
    case "symlink":
      return "importConflictSummaryReasonSymlink";
    case "system_metadata":
      return "importConflictSummaryReasonSystemMetadata";
  }
}
