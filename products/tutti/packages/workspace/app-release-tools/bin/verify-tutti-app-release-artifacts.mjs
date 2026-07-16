#!/usr/bin/env node
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { validateRelease } from "./build-tutti-app-release.mjs";

const catalogSchemaVersion = "tutti.app.catalog.v1";

export async function verifyTuttiAppReleaseArtifacts(options) {
  const releaseFiles = normalizeFiles(options.releaseFiles);
  const catalogFile = options.catalogFile
    ? path.resolve(String(options.catalogFile))
    : null;
  const verifyArtifacts = options.verifyArtifacts !== false;

  if (releaseFiles.length === 0 && !catalogFile) {
    throw new Error(
      "at least one --release-file or --catalog-file is required"
    );
  }

  const releases = [];
  const releasesByAppID = new Map();
  for (const releaseFile of releaseFiles) {
    const release = JSON.parse(await readFile(releaseFile, "utf8"));
    validateRelease(release);
    if (releasesByAppID.has(release.appId)) {
      throw new Error(`duplicate release appId ${release.appId}`);
    }
    releases.push(release);
    releasesByAppID.set(release.appId, release);
  }

  const checks = [];
  for (const release of releases) {
    checks.push({
      appId: release.appId,
      artifactUrl: release.artifactUrl,
      artifactSha256: release.artifactSha256,
      artifactSizeBytes: release.artifactSizeBytes,
      source: `release ${release.appId}`
    });
  }

  if (catalogFile) {
    const catalog = JSON.parse(await readFile(catalogFile, "utf8"));
    validateCatalog(catalog);
    const seenCatalogAppIDs = new Set();
    for (const app of catalog.apps) {
      const appId = app.manifest.appId;
      if (seenCatalogAppIDs.has(appId)) {
        throw new Error(`duplicate catalog appId ${appId}`);
      }
      seenCatalogAppIDs.add(appId);
      const distribution = app.distribution;
      if (!distribution || distribution.kind !== "remote") {
        throw new Error(
          `catalog app ${appId} distribution.kind must be remote`
        );
      }
      for (const key of ["artifactUrl", "artifactSha256", "iconUrl"]) {
        if (
          typeof distribution[key] !== "string" ||
          distribution[key].trim() === ""
        ) {
          throw new Error(
            `catalog app ${appId} distribution.${key} is required`
          );
        }
      }
      requireSHA256Hex(
        distribution.artifactSha256,
        `catalog app ${appId} distribution.artifactSha256`
      );

      const release = releasesByAppID.get(appId);
      if (release) {
        assertCatalogMatchesRelease(app, release);
      }

      checks.push({
        appId,
        artifactUrl: distribution.artifactUrl,
        artifactSha256: distribution.artifactSha256,
        artifactSizeBytes: release?.artifactSizeBytes,
        source: `catalog ${appId}`
      });
    }
  }

  if (verifyArtifacts) {
    const artifactDigests = new Map();
    for (const check of checks) {
      let digest = artifactDigests.get(check.artifactUrl);
      if (!digest) {
        digest = await digestArtifact(check.artifactUrl);
        artifactDigests.set(check.artifactUrl, digest);
      }
      if (digest.sha256 !== check.artifactSha256.toLowerCase()) {
        throw new Error(
          `${check.source} artifact sha256 mismatch: want ${check.artifactSha256} got ${digest.sha256}`
        );
      }
      if (
        Number.isSafeInteger(check.artifactSizeBytes) &&
        digest.size !== check.artifactSizeBytes
      ) {
        throw new Error(
          `${check.source} artifact size mismatch: want ${check.artifactSizeBytes} got ${digest.size}`
        );
      }
    }
  }

  return {
    catalogFile,
    releaseFiles,
    checkedArtifactCount: verifyArtifacts
      ? new Set(checks.map((check) => check.artifactUrl)).size
      : 0
  };
}

function assertCatalogMatchesRelease(app, release) {
  const appId = release.appId;
  const distribution = app.distribution;
  if (app.manifest.version !== release.version) {
    throw new Error(
      `catalog app ${appId} manifest.version must match release version`
    );
  }
  if (distribution.artifactUrl !== release.artifactUrl) {
    throw new Error(
      `catalog app ${appId} artifactUrl must match latest release metadata`
    );
  }
  if (distribution.artifactSha256 !== release.artifactSha256) {
    throw new Error(
      `catalog app ${appId} artifactSha256 must match latest release metadata`
    );
  }
  if (distribution.iconUrl !== release.iconUrl) {
    throw new Error(
      `catalog app ${appId} iconUrl must match latest release metadata`
    );
  }
  if (
    JSON.stringify(app.localizations ?? []) !==
    JSON.stringify(release.localizations ?? [])
  ) {
    throw new Error(
      `catalog app ${appId} localizations must match latest release metadata`
    );
  }
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

async function digestArtifact(artifactUrl) {
  const url = String(artifactUrl).trim();
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return digestHTTPArtifact(url);
  }
  if (url.startsWith("file://")) {
    return digestFileArtifact(fileURLToPath(url));
  }
  return digestFileArtifact(path.resolve(url));
}

async function digestHTTPArtifact(url) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await digestHTTPArtifactOnce(url);
    } catch (error) {
      lastError = error;
      if (attempt < 3) {
        await delay(1000 * attempt);
      }
    }
  }
  throw lastError;
}

async function digestHTTPArtifactOnce(url) {
  const response = await fetch(url);
  if (!response.ok || !response.body) {
    throw new Error(
      `download artifact failed: ${url}: HTTP ${response.status}`
    );
  }
  const hash = createHash("sha256");
  let size = 0;
  for await (const chunk of response.body) {
    const buffer = Buffer.from(chunk);
    hash.update(buffer);
    size += buffer.length;
  }
  return {
    sha256: hash.digest("hex"),
    size
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function digestFileArtifact(filePath) {
  const hash = createHash("sha256");
  let size = 0;
  await new Promise((resolve, reject) => {
    const stream = createReadStream(filePath);
    stream.on("data", (chunk) => {
      hash.update(chunk);
      size += chunk.length;
    });
    stream.on("error", reject);
    stream.on("end", resolve);
  });
  return {
    sha256: hash.digest("hex"),
    size
  };
}

function normalizeFiles(value) {
  const files = Array.isArray(value)
    ? value
    : String(value ?? "")
        .split(/[\n,]/)
        .map((file) => file.trim())
        .filter(Boolean);
  return files.map((file) => path.resolve(file));
}

function requireSHA256Hex(value, label) {
  if (!/^[a-f0-9]{64}$/i.test(String(value ?? ""))) {
    throw new Error(`${label} must be a sha256 hex digest`);
  }
}

function parseArgs(argv) {
  const result = {
    releaseFiles: [],
    verifyArtifacts: true
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
    if (arg === "--catalog-file") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("missing value for --catalog-file");
      }
      result.catalogFile = value;
      index += 1;
      continue;
    }
    if (arg === "--skip-artifact-download") {
      result.verifyArtifacts = false;
      continue;
    }
    throw new Error(`unexpected argument: ${arg}`);
  }
  return result;
}

export async function main() {
  const result = await verifyTuttiAppReleaseArtifacts(
    parseArgs(process.argv.slice(2))
  );
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
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
