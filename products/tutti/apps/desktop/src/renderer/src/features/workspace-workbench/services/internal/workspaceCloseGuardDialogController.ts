import type { WorkbenchHostCloseDialogRequest } from "@tutti-os/workbench-surface";
import { WorkspaceCloseGuardCancelledReporter } from "../../../analytics/reporters/workspace-close-guard-cancelled/workspaceCloseGuardCancelledReporter.ts";
import { WorkspaceCloseGuardConfirmedReporter } from "../../../analytics/reporters/workspace-close-guard-confirmed/workspaceCloseGuardConfirmedReporter.ts";
import { WorkspaceCloseGuardShownReporter } from "../../../analytics/reporters/workspace-close-guard-shown/workspaceCloseGuardShownReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";

export interface WorkspaceCloseGuardDialogSnapshot {
  request: WorkbenchHostCloseDialogRequest | null;
}

export interface WorkspaceCloseGuardDialogController {
  cancel: () => void;
  confirm: () => void;
  dispose: () => void;
  getSnapshot: () => WorkspaceCloseGuardDialogSnapshot;
  requestConfirmation: (
    request: WorkbenchHostCloseDialogRequest
  ) => Promise<boolean>;
  subscribe: (listener: () => void) => () => void;
}

export interface WorkspaceCloseGuardDialogControllerDependencies {
  reporterService?: Pick<IReporterService, "trackEvents">;
  reporterNow?: () => number;
}

export function createWorkspaceCloseGuardDialogController(
  dependencies: WorkspaceCloseGuardDialogControllerDependencies = {}
): WorkspaceCloseGuardDialogController {
  let pendingRequest: PendingCloseGuardDialogRequest | null = null;
  let snapshot = createSnapshot(null);
  const listeners = new Set<() => void>();

  const notify = () => {
    for (const listener of listeners) {
      listener();
    }
  };
  const setRequest = (request: WorkbenchHostCloseDialogRequest | null) => {
    if (snapshot.request === request) {
      return;
    }

    snapshot = createSnapshot(request);
    notify();
  };
  const settle = (confirmed: boolean) => {
    if (!pendingRequest) {
      return;
    }

    reportCloseGuardResult(confirmed, dependencies);
    const { resolve } = pendingRequest;
    pendingRequest = null;
    setRequest(null);
    resolve(confirmed);
  };

  return {
    cancel: () => {
      settle(false);
    },
    confirm: () => {
      settle(true);
    },
    dispose: () => {
      settle(false);
    },
    getSnapshot: () => snapshot,
    requestConfirmation: (request) =>
      new Promise<boolean>((resolve) => {
        pendingRequest?.resolve(false);
        pendingRequest = {
          resolve
        };
        setRequest(request);
        reportCloseGuardShown(dependencies);
      }),
    subscribe: (listener) => {
      listeners.add(listener);

      return () => {
        listeners.delete(listener);
      };
    }
  };
}

interface PendingCloseGuardDialogRequest {
  resolve: (confirmed: boolean) => void;
}

function createSnapshot(
  request: WorkbenchHostCloseDialogRequest | null
): WorkspaceCloseGuardDialogSnapshot {
  return {
    request
  };
}

function reportCloseGuardShown(
  dependencies: WorkspaceCloseGuardDialogControllerDependencies
): void {
  if (!dependencies.reporterService) {
    return;
  }

  void new WorkspaceCloseGuardShownReporter(
    {},
    {
      reporterService: dependencies.reporterService,
      now: dependencies.reporterNow
    }
  ).report();
}

function reportCloseGuardResult(
  confirmed: boolean,
  dependencies: WorkspaceCloseGuardDialogControllerDependencies
): void {
  if (!dependencies.reporterService) {
    return;
  }

  const reporterDependencies = {
    reporterService: dependencies.reporterService,
    now: dependencies.reporterNow
  };
  if (confirmed) {
    void new WorkspaceCloseGuardConfirmedReporter(
      {},
      reporterDependencies
    ).report();
    return;
  }

  void new WorkspaceCloseGuardCancelledReporter(
    {},
    reporterDependencies
  ).report();
}
