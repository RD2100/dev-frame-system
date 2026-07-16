import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";

export function resolveNpmCliJs() {
  const nodeDir = dirname(process.execPath);
  const cliPath = join(nodeDir, "node_modules", "npm", "bin", "npm-cli.js");
  if (!existsSync(cliPath)) {
    throw new Error(
      `npm CLI entry point not found at expected path: ${cliPath}`
    );
  }
  return cliPath;
}

export function resolveNpmInvocation(platform = process.platform) {
  if (platform === "win32") {
    return { command: process.execPath, args: [resolveNpmCliJs()] };
  }
  return { command: "npm", args: [] };
}

export function execNpmSync(args, options = {}) {
  const { command, args: baseArgs } = resolveNpmInvocation();
  return execFileSync(command, [...baseArgs, ...args], options);
}
