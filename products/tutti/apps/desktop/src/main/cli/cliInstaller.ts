import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { chmod, mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveDesktopDefaultsFromEnv } from "../defaults.ts";

export interface DesktopCliShimState {
  installed: boolean;
  shimPath: string;
}

export interface EnsureDesktopCliShimOptions {
  goBin?: string;
  isPackaged?: boolean;
  platform?: NodeJS.Platform;
  repoRoot?: string;
  resourcesPath?: string;
  stateRootDir?: string;
}

export async function ensureDesktopCliShim(
  options: EnsureDesktopCliShimOptions = {}
): Promise<DesktopCliShimState> {
  const isPackaged = options.isPackaged ?? false;
  const platform = options.platform ?? process.platform;
  const resourcesPath = options.resourcesPath ?? process.resourcesPath;
  const stateRootDir =
    options.stateRootDir ?? resolveDesktopDefaultsFromEnv().state.rootDir;
  const binaryName = platform === "win32" ? "tutti.exe" : "tutti";
  const packagedCliPath = join(resourcesPath, "bin", binaryName);
  const shimPath = resolveUserShimPath(stateRootDir, platform, {
    development: !isPackaged
  });

  if (!isPackaged) {
    const repoRoot = options.repoRoot ?? resolveRepoRoot();
    const builtCliPath = join(
      repoRoot,
      "apps",
      "cli",
      "build",
      "dev",
      binaryName
    );
    ensureDevCliBinary({
      goBin: options.goBin,
      platform,
      repoRoot,
      targetPath: builtCliPath
    });
    await mkdir(join(stateRootDir, "bin"), { recursive: true });
    if (platform === "win32") {
      await writeWindowsShim(shimPath, builtCliPath, stateRootDir, {
        development: true
      });
    } else {
      await writeUnixShim(shimPath, builtCliPath, stateRootDir, {
        development: true
      });
    }
    return {
      installed: true,
      shimPath
    };
  }

  await mkdir(join(stateRootDir, "bin"), { recursive: true });
  if (platform === "win32") {
    await writeWindowsShim(shimPath, packagedCliPath, stateRootDir);
  } else {
    await writeUnixShim(shimPath, packagedCliPath, stateRootDir);
  }

  return {
    installed: true,
    shimPath
  };
}

export function resolveUserShimPath(
  stateRootDir: string,
  platform: NodeJS.Platform = process.platform,
  options: { development?: boolean } = {}
): string {
  const commandName = options.development ? "tutti-dev" : "tutti";
  return join(
    stateRootDir,
    "bin",
    platform === "win32" ? `${commandName}.cmd` : commandName
  );
}

async function writeUnixShim(
  shimPath: string,
  packagedCliPath: string,
  stateRootDir: string,
  options: { development?: boolean } = {}
): Promise<void> {
  await rm(shimPath, { force: true, recursive: false });
  await writeFile(
    shimPath,
    [
      "#!/usr/bin/env sh",
      options.development ? "# Tutti dev CLI shim" : "# Tutti CLI shim",
      `if [ -z "\${TUTTI_STATE_DIR:-}" ]; then export TUTTI_STATE_DIR=${shellQuoteValue(stateRootDir)}; fi`,
      `exec ${shellQuoteValue(packagedCliPath)} "$@"`,
      ""
    ].join("\n"),
    "utf8"
  );
  await chmod(shimPath, 0o755);
}

async function writeWindowsShim(
  shimPath: string,
  packagedCliPath: string,
  stateRootDir: string,
  options: { development?: boolean } = {}
): Promise<void> {
  const body = [
    "@echo off",
    options.development ? "rem Tutti dev CLI shim" : "rem Tutti CLI shim",
    `if "%TUTTI_STATE_DIR%"=="" set "TUTTI_STATE_DIR=${stateRootDir}"`,
    `"${packagedCliPath}" %*`,
    ""
  ].join("\r\n");
  await writeFile(shimPath, body, "utf8");
  await chmod(shimPath, 0o755);
}

function shellQuoteValue(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function ensureDevCliBinary(input: {
  goBin?: string;
  platform: NodeJS.Platform;
  repoRoot: string;
  targetPath: string;
}): void {
  if (existsSync(input.targetPath)) {
    return;
  }

  const cliDir = join(input.repoRoot, "apps", "cli");
  mkdirSync(dirname(input.targetPath), { recursive: true });
  const result = spawnSync(
    resolveCommand(
      input.goBin?.trim() || process.env.GO_BIN?.trim() || "go",
      input.platform
    ),
    ["build", "-o", input.targetPath, "./cmd/tutti"],
    {
      cwd: cliDir,
      env: {
        ...process.env,
        TUTTI_ENV: "development"
      },
      stdio: "inherit"
    }
  );
  if (result.status !== 0) {
    throw new Error(
      `go build failed while installing tutti-dev with exit code ${
        result.status ?? "unknown"
      }`
    );
  }
}

function resolveCommand(command: string, platform: NodeJS.Platform): string {
  if (platform === "win32" && !command.toLowerCase().endsWith(".cmd")) {
    return `${command}.cmd`;
  }
  return command;
}

function resolveRepoRoot(): string {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  let candidate = currentDir;
  for (;;) {
    if (
      existsSync(join(candidate, "pnpm-workspace.yaml")) &&
      existsSync(join(candidate, "services", "tuttid"))
    ) {
      return candidate;
    }

    const parent = dirname(candidate);
    if (parent === candidate) {
      return resolve(currentDir, "../../../../");
    }
    candidate = parent;
  }
}
