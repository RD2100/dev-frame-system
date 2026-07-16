import { execFileSync } from "node:child_process";

import { workspaceRoot } from "./npm-release-packages.mjs";
import { computeNextStablePackageReleaseVersion } from "./package-release-version.mjs";

const output = execFileSync("git", ["tag", "--list", "packages-v*"], {
  cwd: workspaceRoot,
  encoding: "utf8"
});
const tagNames = output
  .split("\n")
  .map((tagName) => tagName.trim())
  .filter(Boolean);
const nextVersion = computeNextStablePackageReleaseVersion(tagNames);

process.stdout.write(`${nextVersion}\n`);
