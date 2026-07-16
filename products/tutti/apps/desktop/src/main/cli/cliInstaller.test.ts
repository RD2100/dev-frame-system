import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { ensureDesktopCliShim, resolveUserShimPath } from "./cliInstaller.ts";

test("ensureDesktopCliShim writes dev tutti-dev shim outside packaged app", async () => {
  const stateRootDir = await mkdtemp(join(tmpdir(), "tutti-cli-state-"));
  const repoRoot = await mkdtemp(join(tmpdir(), "tutti-cli-repo-"));
  const builtCliPath = join(repoRoot, "apps", "cli", "build", "dev", "tutti");
  await mkdir(dirname(builtCliPath), { recursive: true });
  await writeFile(builtCliPath, "#!/bin/sh\n", "utf8");

  const state = await ensureDesktopCliShim({
    isPackaged: false,
    platform: "darwin",
    repoRoot,
    resourcesPath: "/Applications/Tutti.app/Contents/Resources",
    stateRootDir
  });

  assert.equal(state.installed, true);
  assert.equal(state.shimPath, join(stateRootDir, "bin", "tutti-dev"));
  const content = await readFile(state.shimPath, "utf8");
  assert.match(content, /Tutti dev CLI shim/);
  assert.match(content, new RegExp(escapeRegExp(builtCliPath)));
});

test("ensureDesktopCliShim writes unix shim with state root", async () => {
  const stateRootDir = await mkdtemp(join(tmpdir(), "tutti-cli-state-"));
  const shimPath = resolveUserShimPath(stateRootDir, "darwin");
  await mkdir(join(stateRootDir, "bin"), { recursive: true });
  await writeFile(shimPath, "stale", "utf8");

  const state = await ensureDesktopCliShim({
    isPackaged: true,
    platform: "darwin",
    resourcesPath: "/Applications/Tutti.app/Contents/Resources",
    stateRootDir
  });

  assert.equal(state.installed, true);
  const content = await readFile(shimPath, "utf8");
  assert.match(content, /Tutti CLI shim/);
  assert.match(
    content,
    /\/Applications\/Tutti\.app\/Contents\/Resources\/bin\/tutti/
  );
  assert.match(content, new RegExp(escapeRegExp(stateRootDir)));
});

test("ensureDesktopCliShim writes windows command shim", async () => {
  const stateRootDir = await mkdtemp(join(tmpdir(), "tutti-cli-state-"));

  const state = await ensureDesktopCliShim({
    isPackaged: true,
    platform: "win32",
    resourcesPath: "C:\\Program Files\\Tutti\\resources",
    stateRootDir
  });

  assert.equal(state.installed, true);
  assert.equal(state.shimPath, join(stateRootDir, "bin", "tutti.cmd"));
  const content = await readFile(state.shimPath, "utf8");
  assert.match(content, /tutti\.exe/);
  assert.match(content, new RegExp(escapeRegExp(stateRootDir)));
});

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
