import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptsDirectory = dirname(fileURLToPath(import.meta.url));
const setupDevPath = join(scriptsDirectory, "setup-dev.mjs");

test("setup-dev accepts the Corepack integrity suffix on packageManager", () => {
  const result = spawnSync(process.execPath, [setupDevPath, "--only=pnpm"], {
    cwd: join(scriptsDirectory, "..", ".."),
    encoding: "utf8"
  });

  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.match(result.stdout, /PASS pnpm: found 10\.11\.0/);
});
