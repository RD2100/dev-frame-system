import assert from "node:assert/strict";
import test from "node:test";
import { createI18nRuntime } from "@tutti-os/ui-i18n-runtime";
import {
  createWorkspaceFileManagerI18nRuntime,
  workspaceFileManagerI18nResources
} from "../../i18n/workspaceFileManagerI18n.ts";
import { createWorkspaceFileManagerStore } from "./workspaceFileManagerStore.ts";
import { WorkspaceFileManagerImportController } from "./workspaceFileManagerImportController.ts";
import type { WorkspaceFileManagerHostActionResult } from "../workspaceFileManagerHostTypes.ts";
import type { WorkspaceFileManagerCapabilities } from "../workspaceFileManagerTypes.ts";
import type { WorkspaceFileManagerHost } from "../workspaceFileManagerHost.interface.ts";

test("importFiles returns unsupported when host import is unavailable", async () => {
  const store = createTestStore();
  const applied: Array<WorkspaceFileManagerHostActionResult | void> = [];
  let refreshCalls = 0;
  const controller = new WorkspaceFileManagerImportController({
    applyHostActionResult: (result) => {
      applied.push(result);
    },
    copy: createTestI18nRuntime,
    host: createHost(),
    refresh: async () => {
      refreshCalls += 1;
    },
    resolveErrorMessage: defaultResolveErrorMessage,
    store
  });

  const result = await controller.importFiles("/workspace");

  assert.equal(result.supported, false);
  assert.equal(result.title, "Import not available yet");
  assert.equal(
    result.message,
    "Importing local files into the workspace is not wired up in this desktop build yet."
  );
  assert.equal(applied.length, 1);
  assert.equal(refreshCalls, 0);
  assert.equal(store.busyAction, null);
});

test("importDroppedFiles returns early when no source paths are resolved", async () => {
  const store = createTestStore();
  const applied: Array<WorkspaceFileManagerHostActionResult | void> = [];
  let importCalls = 0;
  const controller = new WorkspaceFileManagerImportController({
    applyHostActionResult: (result) => {
      applied.push(result);
    },
    copy: createTestI18nRuntime,
    host: createHost({
      resolveDroppedPaths() {
        return [];
      },
      async importPaths() {
        importCalls += 1;
        return { supported: true };
      }
    }),
    refresh: async () => {},
    resolveErrorMessage: defaultResolveErrorMessage,
    store
  });

  const result = await controller.importDroppedFiles(
    createEmptyDataTransfer(),
    "/workspace"
  );

  assert.deepEqual(result, { supported: true });
  assert.equal(importCalls, 0);
  assert.equal(applied.length, 0);
  assert.equal(store.busyAction, null);
});

test("import conflict confirm refreshes and reapplies the confirm result", async () => {
  const store = createTestStore();
  const applied: Array<WorkspaceFileManagerHostActionResult | void> = [];
  let refreshCalls = 0;
  let confirmCalls = 0;
  const controller = new WorkspaceFileManagerImportController({
    applyHostActionResult: (result) => {
      applied.push(result);
    },
    copy: createTestI18nRuntime,
    host: createHost(),
    refresh: async () => {
      refreshCalls += 1;
    },
    resolveErrorMessage: defaultResolveErrorMessage,
    store
  });

  store.importConflictDialog = {
    conflicts: [
      {
        conflictKind: "replaceable",
        destinationKind: "file",
        destinationPath: "/workspace/conflict.txt",
        name: "conflict.txt",
        sourcePath: "/tmp/conflict.txt"
      }
    ],
    onConfirm: async () => {
      confirmCalls += 1;
      return { supported: true };
    }
  };

  await controller.confirmImportConflict();

  assert.equal(confirmCalls, 1);
  assert.equal(refreshCalls, 0);
  assert.equal(applied.length, 1);
  assert.equal(applied[0]?.supported, true);
  assert.equal(store.importConflictDialog, null);
  assert.equal(store.busyAction, null);
});

test("importFiles refreshes after success", async () => {
  const store = createTestStore();
  const applied: Array<WorkspaceFileManagerHostActionResult | void> = [];
  let refreshCalls = 0;
  const importCalls: Array<{
    workspaceID: string;
    targetDirectoryPath: string;
  }> = [];

  const controller = new WorkspaceFileManagerImportController({
    applyHostActionResult: (result) => {
      applied.push(result);
    },
    copy: createTestI18nRuntime,
    host: createHost({
      async importFiles(workspaceID, targetDirectoryPath) {
        importCalls.push({ targetDirectoryPath, workspaceID });
        return { supported: true };
      }
    }),
    refresh: async () => {
      refreshCalls += 1;
    },
    resolveErrorMessage: defaultResolveErrorMessage,
    store
  });

  const result = await controller.importFiles("/workspace/src");

  assert.deepEqual(importCalls, [
    { targetDirectoryPath: "/workspace/src", workspaceID: "workspace-1" }
  ]);
  assert.equal(result.supported, true);
  assert.equal(refreshCalls, 1);
  assert.equal(applied.length, 1);
  assert.equal(store.busyAction, null);
});

test("importFiles converts thrown errors into unsupported import results", async () => {
  const store = createTestStore();
  const applied: Array<WorkspaceFileManagerHostActionResult | void> = [];
  let refreshCalls = 0;
  const controller = new WorkspaceFileManagerImportController({
    applyHostActionResult: (result) => {
      applied.push(result);
    },
    copy: createTestI18nRuntime,
    host: createHost({
      async importFiles() {
        throw new Error("import blew up");
      }
    }),
    refresh: async () => {
      refreshCalls += 1;
    },
    resolveErrorMessage: defaultResolveErrorMessage,
    store
  });

  const result = await controller.importFiles("/workspace");

  assert.equal(result.supported, false);
  assert.equal(result.title, "Import failed");
  assert.equal(result.message, "import blew up");
  assert.equal(refreshCalls, 0);
  assert.equal(applied.length, 1);
  assert.equal(store.busyAction, null);
});

test("importFiles wraps conflicts so confirm triggers a refresh", async () => {
  const store = createTestStore();
  let refreshCalls = 0;
  let confirmCalls = 0;
  const applied: Array<WorkspaceFileManagerHostActionResult | void> = [];
  const controller = new WorkspaceFileManagerImportController({
    applyHostActionResult: (result) => {
      applied.push(result);
    },
    copy: createTestI18nRuntime,
    host: createHost({
      async importFiles() {
        return {
          supported: true,
          importConflict: {
            conflicts: [
              {
                conflictKind: "replaceable",
                destinationKind: "file",
                destinationPath: "/workspace/conflict.txt",
                name: "conflict.txt",
                sourcePath: "/tmp/conflict.txt"
              }
            ],
            onConfirm: async () => {
              confirmCalls += 1;
              return { supported: true };
            }
          }
        };
      }
    }),
    refresh: async () => {
      refreshCalls += 1;
    },
    resolveErrorMessage: defaultResolveErrorMessage,
    store
  });

  const result = await controller.importFiles("/workspace");
  assert.ok(result.importConflict?.onConfirm);
  assert.equal(refreshCalls, 0);

  const confirmResult = await result.importConflict?.onConfirm?.();
  assert.equal(confirmCalls, 1);
  assert.equal(confirmResult?.supported, true);
  assert.equal(refreshCalls, 1);
  assert.equal(applied.length, 1);
});

function createTestI18nRuntime() {
  return createWorkspaceFileManagerI18nRuntime(
    createI18nRuntime({
      dictionaries: [workspaceFileManagerI18nResources.en]
    })
  );
}

function createTestStore(
  capabilities: WorkspaceFileManagerCapabilities = {
    canCopy: false,
    canCreateDirectory: false,
    canCreateFile: false,
    canDelete: false,
    canExport: false,
    canImportFromDrop: false,
    canImportFromPicker: false,
    canMove: false,
    canOpenInAppBrowser: false,
    canOpenInDefaultBrowser: false,
    canOpenWith: false,
    canPickOtherOpenWithApplication: false,
    canRevealInFolder: false,
    canRename: false,
    canSearch: false
  }
) {
  return createWorkspaceFileManagerStore({
    capabilities,
    workspaceID: "workspace-1"
  });
}

function createHost(overrides: Partial<WorkspaceFileManagerHost> = {}) {
  return {
    async listDirectory(input) {
      return {
        directoryPath: input.path,
        entries: [],
        root: "/workspace",
        workspaceID: input.workspaceID
      };
    },
    ...overrides
  } satisfies WorkspaceFileManagerHost;
}

function createEmptyDataTransfer(): Pick<DataTransfer, "files" | "items"> {
  return {
    files: [] as unknown as FileList,
    items: [] as unknown as DataTransferItemList
  };
}

function defaultResolveErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
