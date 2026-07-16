import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

import {
  getNpmReleasePackages,
  workspaceRoot
} from "./npm-release-packages.mjs";
import { parseStablePackageReleaseVersion } from "./package-release-version.mjs";

const releaseVersion = process.argv[2];

if (!releaseVersion) {
  process.stderr.write(
    "Usage: node tools/scripts/apply-ci-package-release-version.mjs <version>\n"
  );
  process.exit(1);
}

if (!parseStablePackageReleaseVersion(releaseVersion)) {
  process.stderr.write(
    `Unsupported package release version: ${releaseVersion}\n`
  );
  process.exit(1);
}

const packages = await getNpmReleasePackages();
const packageNames = new Set(
  packages.map((packageConfig) => packageConfig.name)
);

for (const packageConfig of packages) {
  const manifestPath = join(workspaceRoot, packageConfig.manifestPath);
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));

  manifest.version = releaseVersion;
  updateInternalRanges(manifest, packageNames, releaseVersion);

  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
}

process.stdout.write(
  `Applied CI package release version ${releaseVersion} to ${packages.length} packages\n`
);

function updateInternalRanges(manifest, packageNames, version) {
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
