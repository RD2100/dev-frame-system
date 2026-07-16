import { execFileSync } from "node:child_process";

import {
  getNpmReleasePackages,
  workspaceRoot
} from "./npm-release-packages.mjs";

const packages = await getNpmReleasePackages();
const args = packages.flatMap((packageConfig) => [
  "--filter",
  packageConfig.name
]);

args.push("build");

execFileSync("pnpm", args, {
  cwd: workspaceRoot,
  stdio: "inherit"
});
