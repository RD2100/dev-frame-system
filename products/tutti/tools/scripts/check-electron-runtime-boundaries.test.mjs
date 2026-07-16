import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const scriptPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "check-electron-runtime-boundaries.mjs"
);

test("passes excluded workspace package source imports in Electron runtime code", async () => {
  const workspaceRoot = await createFixtureWorkspace({
    electronExcludePackages: ["@tutti-os/client-tuttid-ts"],
    workspaceFiles: {
      "apps/desktop/src/main/index.ts":
        'import { workspaceProtocolErrorCodes } from "@tutti-os/client-tuttid-ts";\nvoid workspaceProtocolErrorCodes;\n'
    }
  });

  const result = runBoundaryCheck(workspaceRoot);

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /electron runtime boundary check passed/);
});

test("rejects externalized workspace packages that resolve to raw source files", async () => {
  const workspaceRoot = await createFixtureWorkspace({
    electronExcludePackages: ["@tutti-os/client-tuttid-ts"],
    workspaceFiles: {
      "apps/desktop/src/main/index.ts":
        'import { workbenchSnapshotVersion } from "@tutti-os/workbench-snapshot";\nvoid workbenchSnapshotVersion;\n'
    }
  });

  const result = runBoundaryCheck(workspaceRoot);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /electron-runtime-externalized-source/);
  assert.match(result.stderr, /@tutti-os\/workbench-snapshot/);
  assert.match(result.stderr, /externalizeDepsPlugin/);
});

test("rejects mixed workspace package barrels that reach React UI code", async () => {
  const workspaceRoot = await createFixtureWorkspace({
    electronExcludePackages: [
      "@tutti-os/client-tuttid-ts",
      "@tutti-os/workspace-file-manager",
      "@tutti-os/ui-system"
    ],
    workspaceFiles: {
      "apps/desktop/src/main/index.ts":
        'import { filePreviewMaxBytes } from "../shared/runtime.ts";\nvoid filePreviewMaxBytes;\n',
      "apps/desktop/src/shared/runtime.ts":
        'import { workspaceFilePreviewMaxBytes as filePreviewMaxBytes } from "@tutti-os/workspace-file-manager";\nexport { filePreviewMaxBytes };\n'
    }
  });

  const result = runBoundaryCheck(workspaceRoot);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /electron-runtime-ui-leak/);
  assert.match(result.stderr, /@tutti-os\/workspace-file-manager/);
  assert.match(result.stderr, /@tutti-os\/workspace-file-manager\/services/);
});

test("passes narrow non-UI workspace package subpath imports", async () => {
  const workspaceRoot = await createFixtureWorkspace({
    electronExcludePackages: [
      "@tutti-os/client-tuttid-ts",
      "@tutti-os/workspace-file-manager",
      "@tutti-os/ui-system"
    ],
    workspaceFiles: {
      "apps/desktop/src/main/index.ts":
        'import { filePreviewMaxBytes } from "../shared/runtime.ts";\nvoid filePreviewMaxBytes;\n',
      "apps/desktop/src/shared/runtime.ts":
        'import { workspaceFilePreviewMaxBytes as filePreviewMaxBytes } from "@tutti-os/workspace-file-manager/services";\nexport { filePreviewMaxBytes };\n'
    }
  });

  const result = runBoundaryCheck(workspaceRoot);

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /electron runtime boundary check passed/);
});

test("rejects externalized workspace package dependencies reached through bundled packages", async () => {
  const workspaceRoot = await createFixtureWorkspace({
    electronExcludePackages: ["@tutti-os/workspace-file-manager"],
    workspaceFiles: {
      "apps/desktop/src/main/index.ts":
        'import { workspaceFilePreviewMaxBytes } from "@tutti-os/workspace-file-manager/services";\nvoid workspaceFilePreviewMaxBytes;\n',
      "packages/workspace/file-manager/src/services/index.ts":
        'export { workspaceFilePreviewMaxBytes } from "@tutti-os/workspace-file-preview";\n',
      "packages/workspace/file-preview/package.json": JSON.stringify(
        {
          name: "@tutti-os/workspace-file-preview",
          type: "module",
          exports: {
            ".": "./src/index.ts"
          }
        },
        null,
        2
      ),
      "packages/workspace/file-preview/src/index.ts":
        "export const workspaceFilePreviewMaxBytes = 1024;\n"
    }
  });

  const result = runBoundaryCheck(workspaceRoot);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /electron-runtime-externalized-source/);
  assert.match(
    result.stderr,
    /packages\/workspace\/file-preview\/src\/index\.ts/
  );
});

test("passes bundled workspace package dependencies reached through bundled packages", async () => {
  const workspaceRoot = await createFixtureWorkspace({
    electronExcludePackages: [
      "@tutti-os/workspace-file-manager",
      "@tutti-os/workspace-file-preview"
    ],
    workspaceFiles: {
      "apps/desktop/src/main/index.ts":
        'import { workspaceFilePreviewMaxBytes } from "@tutti-os/workspace-file-manager/services";\nvoid workspaceFilePreviewMaxBytes;\n',
      "packages/workspace/file-manager/src/services/index.ts":
        'export { workspaceFilePreviewMaxBytes } from "@tutti-os/workspace-file-preview";\n',
      "packages/workspace/file-preview/package.json": JSON.stringify(
        {
          name: "@tutti-os/workspace-file-preview",
          type: "module",
          exports: {
            ".": "./src/index.ts"
          }
        },
        null,
        2
      ),
      "packages/workspace/file-preview/src/index.ts":
        "export const workspaceFilePreviewMaxBytes = 1024;\n"
    }
  });

  const result = runBoundaryCheck(workspaceRoot);

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /electron runtime boundary check passed/);
});

test("passes excluded non-React ui-system utility subpaths", async () => {
  const workspaceRoot = await createFixtureWorkspace({
    electronExcludePackages: ["@tutti-os/ui-system"],
    workspaceFiles: {
      "apps/desktop/src/main/index.ts":
        'import { cn } from "@tutti-os/ui-system/utils";\nvoid cn;\n'
    }
  });

  const result = runBoundaryCheck(workspaceRoot);

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /electron runtime boundary check passed/);
});

async function createFixtureWorkspace({
  electronExcludePackages = [],
  workspaceFiles = {}
} = {}) {
  const workspaceRoot = await mkdtemp(
    join(tmpdir(), "tutti-electron-runtime-")
  );

  const files = {
    "apps/desktop/electron.vite.config.ts": createElectronViteConfig(
      electronExcludePackages
    ),
    "packages/clients/tuttid-ts/package.json": JSON.stringify(
      {
        name: "@tutti-os/client-tuttid-ts",
        type: "module",
        exports: {
          ".": "./src/index.ts"
        }
      },
      null,
      2
    ),
    "packages/clients/tuttid-ts/src/index.ts":
      "export const workspaceProtocolErrorCodes = { conflict: 'conflict' };\n",
    "packages/workbench/snapshot/package.json": JSON.stringify(
      {
        name: "@tutti-os/workbench-snapshot",
        type: "module",
        exports: {
          ".": "./src/index.ts"
        }
      },
      null,
      2
    ),
    "packages/workbench/snapshot/src/index.ts":
      "export const workbenchSnapshotVersion = 1;\n",
    "packages/workspace/file-manager/package.json": JSON.stringify(
      {
        name: "@tutti-os/workspace-file-manager",
        type: "module",
        exports: {
          ".": "./src/index.ts",
          "./services": "./src/services/index.ts"
        }
      },
      null,
      2
    ),
    "packages/workspace/file-manager/src/index.ts":
      'export { workspaceFilePreviewMaxBytes } from "./services/index.ts";\nexport { WorkspaceFileManager } from "./ui/WorkspaceFileManager.tsx";\n',
    "packages/workspace/file-manager/src/services/index.ts":
      "export const workspaceFilePreviewMaxBytes = 1024;\n",
    "packages/workspace/file-manager/src/ui/WorkspaceFileManager.tsx":
      'import * as React from "react";\nimport { cn } from "@tutti-os/ui-system/utils";\nexport function WorkspaceFileManager() {\n  return React.createElement("div", { className: cn("workspace-file-manager") });\n}\n',
    "packages/ui/system/package.json": JSON.stringify(
      {
        name: "@tutti-os/ui-system",
        type: "module",
        exports: {
          ".": "./src/index.ts",
          "./utils": "./src/lib/utils.ts"
        }
      },
      null,
      2
    ),
    "packages/ui/system/src/index.ts":
      'export * from "./components/index.ts";\nexport * from "./lib/utils.ts";\n',
    "packages/ui/system/src/components/index.ts":
      'export * from "./Button.tsx";\n',
    "packages/ui/system/src/components/Button.tsx":
      'import * as React from "react";\nexport function Button() {\n  return React.createElement("button");\n}\n',
    "packages/ui/system/src/lib/utils.ts":
      "export function cn(...values) { return values.filter(Boolean).join(' '); }\n",
    "apps/desktop/src/preload/entries/main.ts": "export const preload = true;\n"
  };

  for (const [path, content] of Object.entries({
    ...files,
    ...workspaceFiles
  })) {
    const absolutePath = join(workspaceRoot, path);
    await mkdir(dirname(absolutePath), { recursive: true });
    await writeFile(absolutePath, content, "utf8");
  }

  return workspaceRoot;
}

function createElectronViteConfig(excludePackages) {
  const formattedPackages = excludePackages
    .map((packageName) => `"${packageName}"`)
    .join(", ");

  return `
    import { externalizeDepsPlugin } from "electron-vite";

    const runtimeDeps = externalizeDepsPlugin({
      exclude: [${formattedPackages}]
    });

    export default {
      main: {
        plugins: [runtimeDeps]
      },
      preload: {
        plugins: [runtimeDeps]
      }
    };
  `;
}

function runBoundaryCheck(workspaceRoot) {
  return spawnSync(process.execPath, [scriptPath], {
    cwd: workspaceRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      TUTTI_WORKSPACE_ROOT: workspaceRoot
    }
  });
}
