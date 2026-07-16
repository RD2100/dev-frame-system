import assert from "node:assert/strict";
import test from "node:test";

import {
  execNpmSync,
  resolveNpmCliJs,
  resolveNpmInvocation
} from "./runNpm.mjs";

test("execNpmSync resolves npm on the current platform", () => {
  const version = execNpmSync(["--version"], { encoding: "utf8" }).trim();
  assert.match(version, /^\d+\.\d+\.\d+$/);
});

test("execNpmSync does not interpret shell metacharacters", () => {
  const version = execNpmSync(["--version", "& echo pwned", "| dir", "%OS%"], {
    encoding: "utf8"
  }).trim();
  assert.match(version, /^\d+\.\d+\.\d+$/);
});

test("resolveNpmInvocation win32 returns node + npm-cli.js argv", () => {
  const { command, args } = resolveNpmInvocation("win32");

  assert.equal(command, process.execPath);
  assert.equal(args.length, 1);
  assert.match(args[0], /npm-cli\.js$/);
  assert.equal(args[0], resolveNpmCliJs());
});

test("resolveNpmInvocation non-windows returns npm with no extra args", () => {
  for (const platform of ["darwin", "linux"]) {
    const { command, args } = resolveNpmInvocation(platform);

    assert.equal(command, "npm", `command on ${platform}`);
    assert.deepEqual(args, [], `no extra args on ${platform}`);
  }
});
