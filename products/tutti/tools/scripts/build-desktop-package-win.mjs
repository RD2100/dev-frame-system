#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

const workspaceRoot = resolve(import.meta.dirname, "..", "..");
const appDirectory = join(workspaceRoot, "apps", "desktop");
const daemonBundleDirectory = join(appDirectory, "build", "tuttid");
const cliBundleDirectory = join(appDirectory, "build", "tutti");
const pnpmCliPath = process.env.npm_execpath;
const previewBuild = parsePreviewBuild(process.argv.slice(2));

if (process.platform !== "win32") {
  throw new Error("Windows desktop packaging must run on a Windows host");
}
if (!pnpmCliPath || !existsSync(pnpmCliPath)) {
  throw new Error(
    "Windows desktop packaging must be started through the pinned pnpm script"
  );
}

runPhase("prepare_builtin_apps", () =>
  runPnpm(["generate:builtin-apps"], workspaceRoot)
);
runPhase("prepare_packaged_daemon", preparePackagedDaemon);
runPhase("prepare_browser_mcp", () =>
  runNode(join(appDirectory, "scripts", "vendor-browser-mcp.mjs"))
);
runPhase("prepare_claude_sdk_sidecar", () =>
  runNode(join(appDirectory, "scripts", "vendor-claude-sdk-sidecar.mjs"))
);
runPhase("prepare_windows_node_runtime", () =>
  runNode(join(appDirectory, "scripts", "vendor-windows-node-runtime.mjs"))
);

const desktopBuildVersion = runPhase("resolve_desktop_build_version", () =>
  captureNode(join(appDirectory, "scripts", "resolve-build-version.mjs"))
);
process.stderr.write(
  `[release-timing] desktop_version=${desktopBuildVersion}\n`
);

runPhase("pnpm_build", () => runPnpm(["build"], appDirectory));
runPhase("electron_builder_win", () =>
  runPnpm(
    [
      "exec",
      "electron-builder",
      "--win",
      ...(previewBuild ? ["--dir", "-c.win.signAndEditExecutable=false"] : []),
      "--publish",
      "never",
      `-c.extraMetadata.version=${desktopBuildVersion}`
    ],
    appDirectory,
    {
      INIT_CWD: workspaceRoot,
      npm_package_json: join(workspaceRoot, "package.json")
    }
  )
);

function parsePreviewBuild(args) {
  for (const arg of args) {
    if (arg !== "--preview") {
      throw new Error(`unsupported Windows packaging argument: ${arg}`);
    }
  }
  return args.includes("--preview");
}

function preparePackagedDaemon() {
  rmSync(daemonBundleDirectory, { recursive: true, force: true });
  rmSync(cliBundleDirectory, { recursive: true, force: true });
  mkdirSync(daemonBundleDirectory, { recursive: true });
  mkdirSync(cliBundleDirectory, { recursive: true });

  run("go", ["build", "-o", join(daemonBundleDirectory, "tuttid.exe"), "."], {
    cwd: join(workspaceRoot, "services", "tuttid")
  });
  run(
    "go",
    ["build", "-o", join(cliBundleDirectory, "tutti.exe"), "./cmd/tutti"],
    { cwd: join(workspaceRoot, "apps", "cli") }
  );
}

function runPnpm(args, cwd, extraEnv = {}) {
  run(process.execPath, [pnpmCliPath, ...args], {
    cwd,
    env: { ...process.env, ...extraEnv }
  });
}

function runNode(scriptPath) {
  run(process.execPath, [scriptPath], { cwd: workspaceRoot });
}

function captureNode(scriptPath) {
  const result = spawnSync(process.execPath, [scriptPath], {
    cwd: workspaceRoot,
    encoding: "utf8",
    env: process.env
  });
  if (result.status !== 0) {
    process.stderr.write(result.stderr ?? "");
    throw new Error(
      `command failed with exit code ${result.status ?? "unknown"}: ${scriptPath}`
    );
  }
  return result.stdout.trim();
}

function run(command, args, options) {
  const result = spawnSync(command, args, {
    ...options,
    stdio: "inherit"
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(
      `command failed with exit code ${result.status ?? "unknown"}: ${command}`
    );
  }
}

function runPhase(name, action) {
  const startedAt = Date.now();
  process.stderr.write(`[release-timing] phase=${name} status=start\n`);
  try {
    const result = action();
    process.stderr.write(
      `[release-timing] phase=${name} status=done elapsed=${Math.round((Date.now() - startedAt) / 1000)}s\n`
    );
    return result;
  } catch (error) {
    process.stderr.write(
      `[release-timing] phase=${name} status=failed elapsed=${Math.round((Date.now() - startedAt) / 1000)}s\n`
    );
    throw error;
  }
}
