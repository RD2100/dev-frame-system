#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const runtimeArtifactSchemaVersion = "tutti.app.runtime-platform.v2";
const runtimeCatalogSchemaVersion = "tutti.app.runtimes.v2";

export async function buildTuttiAppRuntimeCatalog({
  artifactBaseUrl,
  metadataFiles,
  output
}) {
  const baseUrl = normalizeBaseUrl(artifactBaseUrl);
  const metadataPaths = [...metadataFiles];
  if (metadataPaths.length === 0) {
    throw new Error("At least one runtime metadata file is required");
  }

  const catalog = {
    schemaVersion: runtimeCatalogSchemaVersion,
    runtimes: {}
  };
  const seenPlatforms = new Set();
  for (const metadataPath of metadataPaths) {
    const metadata = JSON.parse(await readFile(metadataPath, "utf8"));
    validateRuntimeArtifactMetadata(metadata, metadataPath);
    if (seenPlatforms.has(metadata.platform)) {
      throw new Error(`duplicate runtime platform ${metadata.platform}`);
    }
    seenPlatforms.add(metadata.platform);
    catalog.runtimes[metadata.platform] = {
      version: metadata.runtimeVersion,
      components: Object.fromEntries(
        Object.entries(metadata.components)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([name, component]) => [
            name,
            {
              version: component.version,
              artifactUrl: joinUrl(baseUrl, component.artifactPath),
              artifactSha256: component.artifactSha256,
              artifactSizeBytes: component.artifactSizeBytes
            }
          ])
      ),
      profiles: Object.fromEntries(
        Object.entries(metadata.profiles)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([name, components]) => [name, [...components]])
      )
    };
  }

  const sortedCatalog = {
    schemaVersion: catalog.schemaVersion,
    runtimes: Object.fromEntries(
      Object.entries(catalog.runtimes).sort(([left], [right]) =>
        left.localeCompare(right)
      )
    )
  };
  const outputJSON = `${JSON.stringify(sortedCatalog, null, 2)}\n`;
  if (output) {
    await mkdir(path.dirname(output), { recursive: true });
    await writeFile(output, outputJSON);
  }
  return sortedCatalog;
}

export function validateRuntimeArtifactMetadata(metadata, metadataPath = "") {
  const prefix = metadataPath ? `${metadataPath}: ` : "";
  if (metadata?.schemaVersion !== runtimeArtifactSchemaVersion) {
    throw new Error(`${prefix}unsupported runtime artifact schema version`);
  }
  for (const field of ["runtimeVersion", "platform"]) {
    if (typeof metadata[field] !== "string" || metadata[field].trim() === "") {
      throw new Error(`${prefix}metadata.${field} is required`);
    }
  }
  if (!metadata.components || typeof metadata.components !== "object") {
    throw new Error(`${prefix}metadata.components is required`);
  }
  if (!metadata.profiles || typeof metadata.profiles !== "object") {
    throw new Error(`${prefix}metadata.profiles is required`);
  }
  if (
    !Array.isArray(metadata.profiles.baseline) ||
    metadata.profiles.baseline.length === 0
  ) {
    throw new Error(`${prefix}metadata.profiles.baseline is required`);
  }
  for (const [profileName, profileComponents] of Object.entries(
    metadata.profiles
  )) {
    validateRuntimeArtifactProfile(
      profileName,
      profileComponents,
      metadata.components,
      prefix
    );
  }
  for (const [componentName, component] of Object.entries(
    metadata.components
  )) {
    validateRuntimeArtifactComponent(componentName, component, prefix);
  }
}

function validateRuntimeArtifactProfile(
  profileName,
  profileComponents,
  components,
  prefix
) {
  if (typeof profileName !== "string" || profileName.trim() === "") {
    throw new Error(`${prefix}metadata profile name is invalid`);
  }
  if (!/^[a-z0-9][a-z0-9._-]*[a-z0-9]$/i.test(profileName)) {
    throw new Error(`${prefix}metadata profile name ${profileName} is unsafe`);
  }
  if (!Array.isArray(profileComponents) || profileComponents.length === 0) {
    throw new Error(`${prefix}metadata.profiles.${profileName} is required`);
  }
  const seen = new Set();
  for (const componentName of profileComponents) {
    if (typeof componentName !== "string" || componentName.trim() === "") {
      throw new Error(`${prefix}metadata.profiles.${profileName} is invalid`);
    }
    if (seen.has(componentName)) {
      throw new Error(
        `${prefix}metadata.profiles.${profileName} has duplicate component`
      );
    }
    seen.add(componentName);
    if (!components[componentName]) {
      throw new Error(
        `${prefix}metadata.profiles.${profileName} references missing component ${componentName}`
      );
    }
  }
}

function validateRuntimeArtifactComponent(componentName, component, prefix) {
  if (!/^[a-z0-9][a-z0-9._-]*[a-z0-9]$/i.test(componentName)) {
    throw new Error(
      `${prefix}metadata component name ${componentName} is unsafe`
    );
  }
  for (const field of ["version", "artifactPath", "artifactSha256"]) {
    if (
      typeof component[field] !== "string" ||
      component[field].trim() === ""
    ) {
      throw new Error(
        `${prefix}metadata.components.${componentName}.${field} is required`
      );
    }
  }
  if (!/^[a-z0-9][a-z0-9._/-]*[a-z0-9]$/i.test(component.artifactPath)) {
    throw new Error(
      `${prefix}metadata.components.${componentName}.artifactPath is unsafe`
    );
  }
  if (component.artifactPath.includes("..")) {
    throw new Error(
      `${prefix}metadata.components.${componentName}.artifactPath is unsafe`
    );
  }
  if (!/^[a-f0-9]{64}$/i.test(component.artifactSha256)) {
    throw new Error(
      `${prefix}metadata.components.${componentName}.artifactSha256 must be a sha256 hex digest`
    );
  }
  if (
    !Number.isSafeInteger(component.artifactSizeBytes) ||
    component.artifactSizeBytes <= 0
  ) {
    throw new Error(
      `${prefix}metadata.components.${componentName}.artifactSizeBytes must be a positive integer`
    );
  }
}

function normalizeBaseUrl(value) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error("artifact base URL is required");
  }
  const trimmed = value.trim().replace(/\/+$/u, "");
  const parsed = new URL(trimmed);
  if (parsed.protocol !== "https:") {
    throw new Error("artifact base URL must use https");
  }
  return trimmed;
}

function joinUrl(baseUrl, relativePath) {
  return `${baseUrl}/${relativePath
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/")}`;
}

function parseArgs(argv) {
  const result = {
    metadataFiles: []
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    switch (arg) {
      case "--artifact-base-url":
        result.artifactBaseUrl = argv[++index];
        break;
      case "--metadata-file":
        result.metadataFiles.push(argv[++index]);
        break;
      case "--output":
        result.output = argv[++index];
        break;
      default:
        throw new Error(`Unsupported argument: ${arg}`);
    }
  }
  return result;
}

export async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  await buildTuttiAppRuntimeCatalog(options);
}

const currentPath = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === currentPath) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
