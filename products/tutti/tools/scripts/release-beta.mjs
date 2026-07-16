import { execFileSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

import {
  getNpmReleasePackages,
  workspaceRoot
} from "./npm-release-packages.mjs";

const packages = await getNpmReleasePackages();

const protectedPaths = [
  ".changeset",
  "pnpm-lock.yaml",
  ...packages.map((packageConfig) => packageConfig.manifestPath)
];
const packageNames = new Set(
  packages.map((packageConfig) => packageConfig.name)
);
const originalManifests = new Map();

ensureProtectedPathsClean();
ensureNpmLogin();

try {
  const betaVersion = await applyBetaVersion();

  console.log(`Publishing package beta ${betaVersion}`);
  execFileSync("pnpm", ["release:pack:check"], {
    cwd: workspaceRoot,
    stdio: "inherit"
  });

  for (const packageConfig of packages) {
    console.log(
      `Publishing ${packageConfig.name}@${betaVersion} with beta tag`
    );
    execFileSync(
      "pnpm",
      ["publish", "--access", "public", "--tag", "beta", "--no-git-checks"],
      {
        cwd: join(workspaceRoot, packageConfig.directory),
        stdio: "inherit"
      }
    );
  }
} finally {
  await restoreManifests();
}

function ensureProtectedPathsClean() {
  const output = execFileSync(
    "git",
    ["status", "--porcelain", "--", ...protectedPaths],
    {
      cwd: workspaceRoot,
      encoding: "utf8"
    }
  ).trim();

  if (output.length > 0) {
    console.error(
      "release:beta needs package manifests, lockfiles, and Changesets state to be clean."
    );
    console.error(output);
    process.exit(1);
  }
}

function ensureNpmLogin() {
  try {
    execFileSync("npm", ["whoami"], {
      cwd: workspaceRoot,
      stdio: "ignore"
    });
  } catch {
    console.error("release:beta needs an npm login. Run `npm login` first.");
    process.exit(1);
  }
}

async function applyBetaVersion() {
  const currentVersion = await readCurrentVersion();
  const betaVersion = createBetaVersion(currentVersion);

  for (const packageConfig of packages) {
    const manifestPath = join(workspaceRoot, packageConfig.manifestPath);
    const manifestText = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(manifestText);

    originalManifests.set(manifestPath, manifestText);

    manifest.version = betaVersion;
    updateInternalRanges(manifest, betaVersion);

    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  }

  return betaVersion;
}

async function readCurrentVersion() {
  const manifestText = await readFile(
    join(workspaceRoot, packages[0].manifestPath),
    "utf8"
  );
  const manifest = JSON.parse(manifestText);

  if (typeof manifest.version !== "string") {
    throw new Error(`${packages[0].manifestPath} is missing a string version`);
  }

  return manifest.version;
}

function createBetaVersion(version) {
  const match = /^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)/.exec(version);

  if (!match?.groups) {
    throw new Error(`Cannot create beta version from ${version}`);
  }

  const major = Number(match.groups.major);
  const minor = Number(match.groups.minor);
  const patch = Number(match.groups.patch) + 1;
  const datetime = new Date()
    .toISOString()
    .replace(/[-:TZ.]/g, "")
    .slice(0, 14);

  return `${major}.${minor}.${patch}-beta-${datetime}`;
}

function updateInternalRanges(manifest, version) {
  for (const field of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies"
  ]) {
    const dependencies = manifest[field];

    if (!dependencies || typeof dependencies !== "object") {
      continue;
    }

    for (const dependencyName of Object.keys(dependencies)) {
      if (packageNames.has(dependencyName)) {
        dependencies[dependencyName] = version;
      }
    }
  }
}

async function restoreManifests() {
  for (const [manifestPath, manifestText] of originalManifests) {
    await writeFile(manifestPath, manifestText);
  }
}
