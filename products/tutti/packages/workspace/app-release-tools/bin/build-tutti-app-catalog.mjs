#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import path from "node:path";

import {
  releaseToCatalogApp,
  validateRelease
} from "./build-tutti-app-release.mjs";

const catalogSchemaVersion = "tutti.app.catalog.v1";

export async function buildTuttiAppCatalog(options) {
  const existingCatalogPath = options.existingCatalogPath
    ? path.resolve(String(options.existingCatalogPath))
    : null;
  const releaseFiles = normalizeReleaseFiles(options.releaseFiles);
  const outputPath = path.resolve(
    options.outputPath
      ? String(options.outputPath)
      : "dist/tutti-app-catalog/catalog.json"
  );

  const seenAppIDs = new Set();
  const seenReleaseAppIDs = new Set();
  const appsByID = new Map();

  if (existingCatalogPath) {
    const existingCatalog = JSON.parse(
      await readFile(existingCatalogPath, "utf8")
    );
    validateCatalog(existingCatalog);
    for (const app of existingCatalog.apps) {
      const appID = app.manifest.appId;
      if (seenAppIDs.has(appID)) {
        throw new Error(`duplicate catalog appId ${appID}`);
      }
      seenAppIDs.add(appID);
      appsByID.set(appID, app);
    }
  }

  for (const releaseFile of releaseFiles) {
    const release = JSON.parse(await readFile(releaseFile, "utf8"));
    validateRelease(release);
    if (seenReleaseAppIDs.has(release.appId)) {
      throw new Error(`duplicate release appId ${release.appId}`);
    }
    seenReleaseAppIDs.add(release.appId);
    if (!seenAppIDs.has(release.appId)) {
      seenAppIDs.add(release.appId);
    }
    appsByID.set(release.appId, releaseToCatalogApp(release));
  }

  if (appsByID.size === 0) {
    throw new Error(
      "at least one release file or existing catalog app is required"
    );
  }

  const apps = [...appsByID.values()];
  apps.sort((left, right) =>
    left.manifest.appId.localeCompare(right.manifest.appId)
  );

  const catalog = {
    schemaVersion: catalogSchemaVersion,
    apps
  };

  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(catalog, null, 2)}\n`);
  return { outputPath, catalog };
}

function normalizeReleaseFiles(value) {
  const files = Array.isArray(value)
    ? value
    : String(value ?? "")
        .split(/[\n,]/)
        .map((file) => file.trim())
        .filter(Boolean);
  return files.map((file) => path.resolve(file));
}

function validateCatalog(catalog) {
  if (!catalog || typeof catalog !== "object") {
    throw new Error("catalog must be an object");
  }
  if (catalog.schemaVersion !== catalogSchemaVersion) {
    throw new Error(`catalog schemaVersion must be ${catalogSchemaVersion}`);
  }
  if (!Array.isArray(catalog.apps)) {
    throw new Error("catalog apps must be an array");
  }
  for (const [index, app] of catalog.apps.entries()) {
    if (!app || typeof app !== "object") {
      throw new Error(`catalog apps[${index}] must be an object`);
    }
    if (
      !app.manifest ||
      typeof app.manifest !== "object" ||
      typeof app.manifest.appId !== "string" ||
      app.manifest.appId.trim() === ""
    ) {
      throw new Error(`catalog apps[${index}].manifest.appId is required`);
    }
  }
}

function parseArgs(argv) {
  const result = {
    releaseFiles: []
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--release-file") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("missing value for --release-file");
      }
      result.releaseFiles.push(value);
      index += 1;
      continue;
    }
    if (arg === "--existing-catalog") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("missing value for --existing-catalog");
      }
      result.existingCatalogPath = value;
      index += 1;
      continue;
    }
    if (arg === "--output") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("missing value for --output");
      }
      result.outputPath = value;
      index += 1;
      continue;
    }
    throw new Error(`unexpected argument: ${arg}`);
  }
  return result;
}

export async function main() {
  const result = await buildTuttiAppCatalog(parseArgs(process.argv.slice(2)));
  process.stdout.write(`${JSON.stringify(result.catalog, null, 2)}\n`);
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
