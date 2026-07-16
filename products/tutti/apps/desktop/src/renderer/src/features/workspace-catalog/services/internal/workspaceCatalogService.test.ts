import assert from "node:assert/strict";
import test from "node:test";
import type {
  HealthStatusResponse,
  WorkspaceSummary
} from "@tutti-os/client-tuttid-ts";
import type { ReporterEventInput } from "../../../analytics/services/reporterService.interface.ts";
import type { DesktopWorkspaceCatalogGateway } from "./adapters/desktopWorkspaceCatalogGateway";
import { WorkspaceCatalogService } from "./workspaceCatalogService.ts";

function createWorkspaceSummary(
  overrides: Partial<WorkspaceSummary> = {}
): WorkspaceSummary {
  return {
    id: "workspace-1",
    lastOpenedAt: null,
    name: "Workspace One",
    ...overrides
  };
}

function createHealthStatus(
  overrides: Partial<HealthStatusResponse> = {}
): HealthStatusResponse {
  return {
    service: "tuttid",
    status: "ok",
    ...overrides
  };
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });

  return {
    promise,
    reject,
    resolve
  };
}

function createGateway(
  overrides: Partial<DesktopWorkspaceCatalogGateway> = {}
): DesktopWorkspaceCatalogGateway {
  return {
    async getHealth() {
      return createHealthStatus();
    },
    async getStartupWorkspace() {
      return createWorkspaceSummary();
    },
    async getWorkspace(workspaceID: string) {
      return createWorkspaceSummary({ id: workspaceID });
    },
    async renameWorkspace(workspaceID: string, payload: { name: string }) {
      return createWorkspaceSummary({ id: workspaceID, name: payload.name });
    },
    ...overrides
  };
}

function createReporterService(calls: ReporterEventInput[][] = []) {
  return {
    async trackEvents(events: ReporterEventInput[]) {
      calls.push(events);
    }
  };
}

test("WorkspaceCatalogService falls back to startup workspace without window context", async () => {
  const service = new WorkspaceCatalogService({
    gateway: createGateway(),
    platform: "linux",
    reporterService: createReporterService(),
    reporterNow: () => 1749124800000
  });

  await service.loadWorkspaceWindow(null, "workspace");

  assert.equal(service.store.status, "ready");
  assert.equal(service.store.workspace?.id, "workspace-1");
  assert.equal(service.store.workspaceID, "workspace-1");
  assert.equal(service.store.isLoadingWorkspaces, false);
});

test("WorkspaceCatalogService marks missing workspace context when no startup workspace exists", async () => {
  const service = new WorkspaceCatalogService({
    gateway: createGateway({
      async getStartupWorkspace() {
        return null;
      }
    }),
    platform: "linux",
    reporterService: createReporterService(),
    reporterNow: () => 1749124800000
  });

  await service.loadWorkspaceWindow(null, "workspace");

  assert.equal(service.store.status, "missing-context");
  assert.equal(service.store.workspace, null);
  assert.equal(service.store.workspaceID, null);
  assert.equal(service.store.isLoadingWorkspaces, false);
});

test("WorkspaceCatalogService loads workspace window data and health", async () => {
  const workspace = createWorkspaceSummary({ id: "workspace-9" });
  const reporterCalls: ReporterEventInput[][] = [];
  const service = new WorkspaceCatalogService({
    gateway: createGateway({
      async getWorkspace(workspaceID: string) {
        return { ...workspace, id: workspaceID };
      }
    }),
    platform: "win32",
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => 1749124800000
  });

  await service.loadWorkspaceWindow("workspace-9", "workspace");

  assert.equal(service.store.status, "ready");
  assert.equal(service.store.workspace?.id, "workspace-9");
  assert.equal(service.store.health?.service, "tuttid");
  assert.deepEqual(reporterCalls, [
    [
      {
        clientTS: 1749124800000,
        name: "workspace.opened",
        params: {
          route_view: "workspace"
        }
      }
    ]
  ]);
});

test("WorkspaceCatalogService tracks workspace open failures", async () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const service = new WorkspaceCatalogService({
    gateway: createGateway({
      async getWorkspace() {
        throw Object.assign(new Error("daemon offline"), {
          code: "daemon_unreachable"
        });
      }
    }),
    platform: "linux",
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => 1749124800000
  });

  await service.loadWorkspaceWindow("workspace-404", "workspace");

  assert.equal(service.store.status, "unavailable");
  assert.deepEqual(reporterCalls, [
    [
      {
        clientTS: 1749124800000,
        name: "workspace.open_failed",
        params: {
          error_reason: "daemon_unreachable",
          route_view: "workspace"
        }
      }
    ],
    [
      {
        clientTS: 1749124800000,
        name: "error.workspace_unavailable",
        params: {
          error_type: "daemon_unreachable"
        }
      }
    ]
  ]);
});

test("WorkspaceCatalogService tracks overview retry clicks before retrying", async () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const service = new WorkspaceCatalogService({
    gateway: createGateway({
      async getWorkspace() {
        throw Object.assign(new Error("daemon offline"), {
          code: "daemon_unreachable"
        });
      }
    }),
    platform: "linux",
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => 1749124800000
  });

  await service.loadWorkspaceWindow("workspace-404", "workspace");
  await service.loadWorkspaceWindow("workspace-404", "workspace");

  assert.equal(service.store.status, "unavailable");
  assert.deepEqual(reporterCalls[2], [
    {
      clientTS: 1749124800000,
      name: "workspace.overview.retry_clicked",
      params: {
        catalog_status: "unavailable"
      }
    }
  ]);
});

test("WorkspaceCatalogService ignores stale workspace-window loads", async () => {
  const firstHealth = createDeferred<HealthStatusResponse>();
  const firstWorkspace = createDeferred<WorkspaceSummary>();
  let workspaceCallCount = 0;

  const service = new WorkspaceCatalogService({
    gateway: createGateway({
      getHealth() {
        if (workspaceCallCount === 0) {
          return firstHealth.promise;
        }
        return Promise.resolve(createHealthStatus());
      },
      getWorkspace(workspaceID: string) {
        if (workspaceCallCount++ === 0) {
          return firstWorkspace.promise;
        }
        return Promise.resolve(
          createWorkspaceSummary({ id: workspaceID, name: "Newest Workspace" })
        );
      }
    }),
    platform: "darwin",
    reporterService: createReporterService(),
    reporterNow: () => 1749124800000
  });

  const firstLoad = service.loadWorkspaceWindow("workspace-old", "workspace");
  await Promise.resolve();
  const secondLoad = service.loadWorkspaceWindow("workspace-new", "workspace");
  await secondLoad;

  firstHealth.resolve(createHealthStatus({ service: "stale-tuttid" }));
  firstWorkspace.resolve(
    createWorkspaceSummary({
      id: "workspace-old",
      name: "Old Workspace"
    })
  );
  await firstLoad;

  assert.equal(service.store.workspaceID, "workspace-new");
  assert.equal(service.store.workspace?.id, "workspace-new");
  assert.equal(service.store.workspace?.name, "Newest Workspace");
  assert.equal(service.store.health?.service, "tuttid");
});

test("WorkspaceCatalogService rename updates current workspace", async () => {
  const service = new WorkspaceCatalogService({
    gateway: createGateway(),
    platform: "darwin",
    reporterService: createReporterService(),
    reporterNow: () => 1749124800000
  });

  await service.loadWorkspaceWindow("workspace-1", "workspace");
  await service.renameWorkspace("workspace-1", "Renamed Workspace");

  assert.equal(service.store.workspace?.name, "Renamed Workspace");
  assert.equal(service.store.renamingWorkspaceID, null);
});
