import assert from "node:assert/strict";
import test from "node:test";
import { openWorkspaceOnboardingIfNeeded } from "./useWorkspaceOnboardingAutoOpen.ts";

test("workspace onboarding auto-open uses local app list before refreshing remote catalog", async () => {
  let catalogRefreshCalls = 0;
  const result = await openWorkspaceOnboardingIfNeeded({
    appCenterService: {
      store: {
        apps: [
          {
            appId: "tutti-onboarding",
            installed: true
          }
        ]
      },
      async refresh() {},
      async refreshCatalog() {
        catalogRefreshCalls += 1;
      },
      async installApp() {},
      async openApp() {
        return true;
      }
    },
    wait: async () => {},
    workbenchHostService: createWorkbenchHostService(),
    workspaceId: "workspace-1"
  });

  assert.equal(result, "opened");
  assert.equal(catalogRefreshCalls, 0);
});

test("workspace onboarding auto-open falls back to remote catalog when app is missing locally", async () => {
  let catalogRefreshCalls = 0;
  const apps: { appId: string; installed?: boolean }[] = [];
  const result = await openWorkspaceOnboardingIfNeeded({
    appCenterService: {
      store: {
        apps
      },
      async refresh() {},
      async refreshCatalog() {
        catalogRefreshCalls += 1;
        apps.push({
          appId: "tutti-onboarding",
          installed: true
        });
      },
      async installApp() {},
      async openApp() {
        return true;
      }
    },
    wait: async () => {},
    workbenchHostService: createWorkbenchHostService(),
    workspaceId: "workspace-1"
  });

  assert.equal(result, "opened");
  assert.equal(catalogRefreshCalls, 1);
});

test("workspace onboarding auto-open retries when the first open does not launch", async () => {
  let markCalls = 0;
  let openCalls = 0;
  const result = await openWorkspaceOnboardingIfNeeded({
    appCenterService: {
      store: {
        apps: [
          {
            appId: "tutti-onboarding",
            installed: true
          }
        ]
      },
      async refresh() {},
      async refreshCatalog() {},
      async installApp() {},
      async openApp() {
        openCalls += 1;
        return openCalls === 2;
      }
    },
    wait: async () => {},
    workbenchHostService: createWorkbenchHostService({
      markWorkspaceOnboardingAutoOpened: () => {
        markCalls += 1;
      }
    }),
    workspaceId: "workspace-1"
  });

  assert.equal(result, "opened");
  assert.equal(openCalls, 2);
  assert.equal(markCalls, 1);
});

test("workspace onboarding auto-open exhausts retries without marking when the app never opens", async () => {
  let markCalls = 0;
  let openCalls = 0;
  const result = await openWorkspaceOnboardingIfNeeded({
    appCenterService: {
      store: {
        apps: [
          {
            appId: "tutti-onboarding",
            installed: true
          }
        ]
      },
      async refresh() {},
      async refreshCatalog() {},
      async installApp() {},
      async openApp() {
        openCalls += 1;
        return false;
      }
    },
    maxAttempts: 2,
    wait: async () => {},
    workbenchHostService: createWorkbenchHostService({
      markWorkspaceOnboardingAutoOpened: () => {
        markCalls += 1;
      }
    }),
    workspaceId: "workspace-1"
  });

  assert.equal(result, "not-opened");
  assert.equal(openCalls, 2);
  assert.equal(markCalls, 0);
});

test("workspace onboarding auto-open waits for async install before opening", async () => {
  let installCalls = 0;
  let openCalls = 0;
  let refreshCalls = 0;
  const app = {
    appId: "tutti-onboarding",
    installed: false
  };
  const diagnostics: WorkspaceOnboardingDiagnostic[] = [];
  const result = await openWorkspaceOnboardingIfNeeded({
    appCenterService: {
      store: {
        apps: [app]
      },
      async refresh() {
        refreshCalls += 1;
        if (refreshCalls === 5) {
          app.installed = true;
        }
      },
      async refreshCatalog() {},
      async installApp() {
        installCalls += 1;
      },
      async openApp() {
        openCalls += 1;
        return true;
      }
    },
    maxAttempts: 2,
    maxInstallAttempts: 6,
    wait: async () => {},
    workbenchHostService: createWorkbenchHostService({
      logWorkspaceOnboardingAutoOpenDiagnostic: (diagnostic) => {
        diagnostics.push(diagnostic);
      }
    }),
    workspaceId: "workspace-1"
  });

  assert.equal(result, "opened");
  assert.equal(installCalls, 1);
  assert.equal(openCalls, 1);
  assert.equal(refreshCalls, 6);
  assert.deepEqual(
    diagnostics
      .filter((diagnostic) =>
        [
          "workspace-onboarding.auto-open.install-requested",
          "workspace-onboarding.auto-open.install-request-accepted",
          "workspace-onboarding.auto-open.installed-detected",
          "workspace-onboarding.auto-open.opened"
        ].includes(diagnostic.event)
      )
      .map((diagnostic) => diagnostic.event),
    [
      "workspace-onboarding.auto-open.install-requested",
      "workspace-onboarding.auto-open.install-request-accepted",
      "workspace-onboarding.auto-open.installed-detected",
      "workspace-onboarding.auto-open.opened"
    ]
  );
});

test("workspace onboarding auto-open records launch retry diagnostics", async () => {
  let openCalls = 0;
  const diagnostics: WorkspaceOnboardingDiagnostic[] = [];
  const result = await openWorkspaceOnboardingIfNeeded({
    appCenterService: {
      store: {
        apps: [
          {
            appId: "tutti-onboarding",
            installed: true
          }
        ]
      },
      async refresh() {},
      async refreshCatalog() {},
      async installApp() {},
      async openApp() {
        openCalls += 1;
        return openCalls === 2;
      }
    },
    wait: async () => {},
    workbenchHostService: createWorkbenchHostService({
      logWorkspaceOnboardingAutoOpenDiagnostic: (diagnostic) => {
        diagnostics.push(diagnostic);
      }
    }),
    workspaceId: "workspace-1"
  });

  assert.equal(result, "opened");
  assert.deepEqual(
    diagnostics
      .filter((diagnostic) =>
        [
          "workspace-onboarding.auto-open.launch-not-ready",
          "workspace-onboarding.auto-open.opened"
        ].includes(diagnostic.event)
      )
      .map((diagnostic) => ({
        appId: diagnostic.details?.appId,
        attempt: diagnostic.details?.attempt,
        event: diagnostic.event,
        level: diagnostic.level,
        maxAttempts: diagnostic.details?.maxAttempts
      })),
    [
      {
        appId: "tutti-onboarding",
        attempt: 1,
        event: "workspace-onboarding.auto-open.launch-not-ready",
        level: "warn",
        maxAttempts: 20
      },
      {
        appId: "tutti-onboarding",
        attempt: 2,
        event: "workspace-onboarding.auto-open.opened",
        level: "info",
        maxAttempts: 20
      }
    ]
  );
});

type WorkspaceOnboardingDiagnostic = {
  details?: Record<string, unknown>;
  event: string;
  level: "debug" | "info" | "warn" | "error";
  workspaceId: string;
};

function createWorkbenchHostService(input?: {
  logWorkspaceOnboardingAutoOpenDiagnostic?: (
    diagnostic: WorkspaceOnboardingDiagnostic
  ) => void;
  markWorkspaceOnboardingAutoOpened?: () => void;
}) {
  return {
    async hasWorkspaceOnboardingAutoOpened() {
      return false;
    },
    logWorkspaceOnboardingAutoOpenDiagnostic(
      diagnostic: WorkspaceOnboardingDiagnostic
    ) {
      input?.logWorkspaceOnboardingAutoOpenDiagnostic?.(diagnostic);
    },
    async markWorkspaceOnboardingAutoOpened() {
      input?.markWorkspaceOnboardingAutoOpened?.();
    }
  };
}
