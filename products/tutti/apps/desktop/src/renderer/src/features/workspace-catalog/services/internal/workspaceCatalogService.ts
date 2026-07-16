import type { IWorkspaceCatalogService } from "../workspaceCatalogService.interface";
import { ErrorWorkspaceUnavailableReporter } from "../../../analytics/reporters/error-workspace-unavailable/errorWorkspaceUnavailableReporter.ts";
import { WorkspaceOpenFailedReporter } from "../../../analytics/reporters/workspace-open-failed/workspaceOpenFailedReporter.ts";
import { WorkspaceOpenedReporter } from "../../../analytics/reporters/workspace-opened/workspaceOpenedReporter.ts";
import { WorkspaceOverviewRetryClickedReporter } from "../../../analytics/reporters/workspace-overview-retry-clicked/workspaceOverviewRetryClickedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";
import { getActiveLocale } from "../../../../i18n/runtime.ts";
import {
  getDesktopErrorCode,
  resolveDesktopErrorMessage
} from "../../../../lib/desktopErrors.ts";
import type { DesktopWorkspaceCatalogGateway } from "./adapters/desktopWorkspaceCatalogGateway.ts";
import { createWorkspaceCatalogStore } from "./workspaceCatalogStore.ts";

export interface WorkspaceCatalogServiceDependencies {
  gateway: DesktopWorkspaceCatalogGateway;
  platform: NodeJS.Platform;
  reporterService: Pick<IReporterService, "trackEvents">;
  reporterNow?: () => number;
}

export class WorkspaceCatalogService implements IWorkspaceCatalogService {
  readonly _serviceBrand: undefined;
  readonly store;

  private readonly dependencies: WorkspaceCatalogServiceDependencies;
  private loadSequence = 0;

  constructor(dependencies: WorkspaceCatalogServiceDependencies) {
    this.dependencies = dependencies;
    this.store = createWorkspaceCatalogStore(this.dependencies.platform);
  }

  async loadWorkspaceWindow(
    workspaceID: string | null,
    routeView: string
  ): Promise<void> {
    const sequence = ++this.loadSequence;
    const previousStatus = this.store.status;
    this.resetCatalogErrors();
    this.store.routeView = routeView || "workspace";
    this.store.workspaceID = workspaceID;
    this.store.health = null;
    this.store.healthError = null;
    this.store.workspace = null;
    this.store.workspaceError = null;

    if (previousStatus === "unavailable") {
      await new WorkspaceOverviewRetryClickedReporter(
        {
          catalogStatus: previousStatus
        },
        {
          reporterService: this.dependencies.reporterService,
          now: this.dependencies.reporterNow
        }
      ).report();
    }

    this.store.status = "loading";
    this.store.isLoadingWorkspaces = true;

    if (!workspaceID) {
      const [healthResult, startupWorkspaceResult] = await Promise.allSettled([
        this.dependencies.gateway.getHealth(),
        this.dependencies.gateway.getStartupWorkspace()
      ]);

      if (sequence !== this.loadSequence) {
        return;
      }

      if (healthResult.status === "fulfilled") {
        this.store.health = healthResult.value;
      } else {
        this.store.healthError = formatCatalogError(healthResult.reason);
      }

      this.store.isLoadingWorkspaces = false;

      if (
        startupWorkspaceResult.status === "fulfilled" &&
        startupWorkspaceResult.value
      ) {
        this.store.workspace = startupWorkspaceResult.value;
        this.store.workspaceID = startupWorkspaceResult.value.id;
        this.store.status = "ready";
        await new WorkspaceOpenedReporter(
          {
            routeView: this.store.routeView
          },
          {
            reporterService: this.dependencies.reporterService,
            now: this.dependencies.reporterNow
          }
        ).report();
        return;
      }

      this.store.status = "missing-context";
      this.store.workspaces = [];
      if (startupWorkspaceResult.status === "rejected") {
        this.store.workspaceError = formatCatalogError(
          startupWorkspaceResult.reason
        );
      }
      return;
    }

    const [healthResult, workspaceResult] = await Promise.allSettled([
      this.dependencies.gateway.getHealth(),
      this.dependencies.gateway.getWorkspace(workspaceID)
    ]);

    if (sequence !== this.loadSequence) {
      return;
    }

    if (healthResult.status === "fulfilled") {
      this.store.health = healthResult.value;
    } else {
      this.store.healthError = formatCatalogError(healthResult.reason);
    }

    this.store.isLoadingWorkspaces = false;

    if (workspaceResult.status === "fulfilled") {
      this.store.workspace = workspaceResult.value;
      this.store.status = "ready";
      await new WorkspaceOpenedReporter(
        {
          routeView: this.store.routeView
        },
        {
          reporterService: this.dependencies.reporterService,
          now: this.dependencies.reporterNow
        }
      ).report();
      return;
    }

    this.store.workspaceError = formatCatalogError(workspaceResult.reason);
    this.store.status = "unavailable";
    const errorCode = getDesktopErrorCode(workspaceResult.reason) ?? "unknown";
    await new WorkspaceOpenFailedReporter(
      {
        errorReason: errorCode,
        routeView: this.store.routeView
      },
      {
        reporterService: this.dependencies.reporterService,
        now: this.dependencies.reporterNow
      }
    ).report();
    await new ErrorWorkspaceUnavailableReporter(
      {
        errorType: errorCode
      },
      {
        reporterService: this.dependencies.reporterService,
        now: this.dependencies.reporterNow
      }
    ).report();
  }

  async renameWorkspace(workspaceID: string, name: string): Promise<void> {
    const nextName = name.trim();
    this.store.renameError = null;
    this.store.renamingWorkspaceID = workspaceID;

    try {
      const workspace = await this.dependencies.gateway.renameWorkspace(
        workspaceID,
        { name: nextName }
      );
      if (this.store.workspace?.id === workspace.id) {
        this.store.workspace = workspace;
      }
    } catch (error) {
      this.store.renameError = formatCatalogError(error);
      throw error;
    } finally {
      this.store.renamingWorkspaceID = null;
    }
  }

  private resetCatalogErrors(): void {
    this.store.createError = null;
    this.store.deleteError = null;
    this.store.deletingWorkspaceID = null;
    this.store.openingWorkspaceID = null;
    this.store.renameError = null;
    this.store.renamingWorkspaceID = null;
    this.store.workspacesError = null;
  }
}

function formatCatalogError(error: unknown): string {
  return resolveDesktopErrorMessage(error, getActiveLocale());
}
