#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseReleaseTag } from "./lib/releaseConfig.mjs";

const appDir = resolve(import.meta.dirname, "..");
const packageJsonPath = resolve(appDir, "package.json");
const rawTag = process.argv[2];

if (!rawTag) {
  process.stderr.write(
    "Usage: node scripts/apply-ci-release-version.mjs <git-tag>\n"
  );
  process.exit(1);
}

const releaseVersion = parseReleaseTag(rawTag);
if (!releaseVersion) {
  process.stderr.write(`Invalid release tag: ${rawTag}\n`);
  process.exit(1);
}

const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));
packageJson.version = releaseVersion;
await writeFile(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`);
process.stdout.write(
  `Applied CI release version ${releaseVersion} to package.json\n`
);
