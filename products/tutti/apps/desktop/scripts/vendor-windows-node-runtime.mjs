#!/usr/bin/env node
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  cpSync,
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  renameSync,
  statSync,
  writeFileSync
} from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktopDir = join(__dirname, "..");
const buildDir = join(desktopDir, "build");
const appRuntimeDir = join(buildDir, "app-runtime");
const lockPath = join(
  dirname(dirname(desktopDir)),
  "config",
  "tutti.windows-node-runtime.lock.json"
);
const versionModulePath = join(
  dirname(dirname(desktopDir)),
  "apps",
  "desktop",
  "src",
  "main",
  "daemon",
  "windowsNodeRuntimeVersion.ts"
);

const metadataFileName = ".tutti-runtime-metadata.json";
const metadataSchemaVersion = "tutti.windows-node-runtime-metadata.v1";
const requiredBinaries = ["node.exe", "npm.cmd", "npx.cmd"];
const defaultDownloadTimeoutMs = 300_000;

function log(msg) {
  process.stderr.write(`[vendor-windows-node-runtime] ${msg}\n`);
}

function isRegularFile(path) {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

export function parseLock(content) {
  let parsed;
  try {
    parsed = JSON.parse(content);
  } catch {
    throw new Error("windows node runtime lock is not valid JSON");
  }
  if (
    !parsed ||
    typeof parsed !== "object" ||
    parsed.schemaVersion !== "tutti.windows-node-runtime-lock.v1"
  ) {
    throw new Error(
      "windows node runtime lock schemaVersion must be tutti.windows-node-runtime-lock.v1"
    );
  }
  const node = parsed.node;
  if (!node || typeof node !== "object") {
    throw new Error("windows node runtime lock is missing the node entry");
  }
  const version = String(node.version || "").trim();
  const url = String(node.url || "").trim();
  const sha256 = String(node.sha256 || "").trim();

  if (!version) {
    throw new Error("windows node runtime lock node.version is required");
  }
  if (!/^\d+\.\d+\.\d+$/.test(version)) {
    throw new Error(
      "windows node runtime lock node.version must be a semantic version (X.Y.Z)"
    );
  }
  if (!url) {
    throw new Error("windows node runtime lock node.url is required");
  }
  let urlObj;
  try {
    urlObj = new URL(url);
  } catch {
    throw new Error("windows node runtime lock node.url is not a valid URL");
  }
  if (urlObj.protocol !== "https:") {
    throw new Error("windows node runtime lock node.url must use https");
  }
  if (urlObj.hostname !== "nodejs.org") {
    throw new Error(
      "windows node runtime lock node.url host must be nodejs.org"
    );
  }
  const expectedArchiveName = `node-v${version}-win-x64.zip`;
  if (!urlObj.pathname.endsWith("/" + expectedArchiveName)) {
    throw new Error(
      `windows node runtime lock node.url must end with /${expectedArchiveName}`
    );
  }
  if (!sha256) {
    throw new Error("windows node runtime lock node.sha256 is required");
  }
  if (!/^[0-9a-fA-F]{64}$/.test(sha256)) {
    throw new Error(
      "windows node runtime lock node.sha256 must be 64 hex characters"
    );
  }

  return { version, url, sha256: sha256.toLowerCase() };
}

function readMetadata(root) {
  const metaPath = join(root, "node", metadataFileName);
  try {
    const raw = readFileSync(metaPath, "utf8");
    const meta = JSON.parse(raw);
    if (
      meta &&
      typeof meta === "object" &&
      meta.schemaVersion === metadataSchemaVersion &&
      typeof meta.nodeVersion === "string"
    ) {
      return {
        schemaVersion: meta.schemaVersion,
        nodeVersion: meta.nodeVersion
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function validateWindowsNodeRuntimeRoot(root, expectedNodeVersion) {
  if (!root || typeof root !== "string") {
    return false;
  }
  const nodeDir = join(root, "node");
  const nodeBinDir = join(nodeDir, "bin");

  const meta = readMetadata(root);
  if (!meta) {
    return false;
  }
  if (expectedNodeVersion !== undefined && meta.nodeVersion !== expectedNodeVersion) {
    return false;
  }

  for (const name of requiredBinaries) {
    if (!isRegularFile(join(nodeBinDir, name))) {
      return false;
    }
  }
  if (
    !isRegularFile(join(nodeBinDir, "node_modules", "npm", "bin", "npm-cli.js"))
  ) {
    return false;
  }
  if (!isRegularFile(join(nodeDir, "LICENSE"))) {
    return false;
  }
  if (!isRegularFile(join(nodeDir, metadataFileName))) {
    return false;
  }
  return true;
}

function containsPath(container, path) {
  try {
    const realContainer = realpathSync(container);
    const realPath = realpathSync(path);
    if (realContainer === realPath) return true;
    const rel = relative(realContainer, realPath);
    return rel !== "" && !isAbsolute(rel) && rel !== ".." && !rel.startsWith(".." + sep);
  } catch {
    return false;
  }
}

function isRealDirectory(path) {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function recoverBackup(appRTDir) {
  const ancestor = dirname(appRTDir);
  const backupDir = join(ancestor, ".app-runtime-backup");
  if (!existsSync(backupDir)) {
    return null;
  }
  if (validateWindowsNodeRuntimeRoot(backupDir)) {
    if (existsSync(appRTDir)) {
      rmSync(appRTDir, { recursive: true, force: true });
    }
    renameSync(backupDir, appRTDir);
    return appRTDir;
  }
  rmSync(backupDir, { recursive: true, force: true });
  return null;
}

function defaultExtractImpl({ zipPath, extractDir, version }) {
  const result = spawnSync(
    "powershell",
    [
      "-NoProfile",
      "-Command",
      "Expand-Archive -LiteralPath $env:TUTTI_NODE_ZIP -DestinationPath $env:TUTTI_NODE_DEST -Force"
    ],
    {
      stdio: "inherit",
      env: {
        ...process.env,
        TUTTI_NODE_ZIP: zipPath,
        TUTTI_NODE_DEST: extractDir
      }
    }
  );
  if (result.status !== 0) {
    throw new Error(
      `Expand-Archive failed with exit code ${result.status}`
    );
  }
  return join(extractDir, `node-v${version}-win-x64`);
}

function defaultSwap({ stagingDir, targetDir, renameFn }) {
  const ancestor = dirname(targetDir);
  mkdirSync(ancestor, { recursive: true });
  const backupDir = join(ancestor, ".app-runtime-backup");
  rmSync(backupDir, { recursive: true, force: true });
  if (existsSync(targetDir)) {
    renameFn(targetDir, backupDir);
  }
  try {
    renameFn(stagingDir, targetDir);
  } catch (err) {
    if (existsSync(backupDir)) {
      rmSync(targetDir, { recursive: true, force: true });
      renameFn(backupDir, targetDir);
    }
    throw err;
  }
  rmSync(backupDir, { recursive: true, force: true });
}

export function syncVersionModule(version, modulePath) {
  const targetPath = modulePath || versionModulePath;
  const content = [
    "// Generated from config/tutti.windows-node-runtime.lock.json by",
    "// apps/desktop/scripts/vendor-windows-node-runtime.mjs.",
    "// Single source of expected Windows Node runtime identity",
    "// used by isWindowsNodeRuntimeRootValid at desktop startup.",
    `export const pinnedWindowsNodeVersion = "${version}";`,
    ""
  ].join("\n");

  let existing = "";
  try {
    existing = readFileSync(targetPath, "utf8");
  } catch {}
  if (existing === content) {
    return;
  }

  mkdirSync(dirname(targetPath), { recursive: true });
  writeFileSync(targetPath, content, "utf8");
  log(`synced ${targetPath}`);
}

export async function prepareWindowsNodeRuntime({
  buildDir: buildDirOverride,
  lockContent,
  fetchImpl,
  downloadTimeoutMs,
  extractImpl,
  renameImpl,
} = {}) {
  const bDir = buildDirOverride || buildDir;
  const appRTDir = join(bDir, "app-runtime");
  const fetchFn = fetchImpl || fetch;
  const extractFn = extractImpl || defaultExtractImpl;
  const innerRename = renameImpl || renameSync;
  const timeout = downloadTimeoutMs ?? defaultDownloadTimeoutMs;

  const { version, url, sha256 } = parseLock(lockContent);

  syncVersionModule(version);

  if (validateWindowsNodeRuntimeRoot(appRTDir, version)) {
    return;
  }

  recoverBackup(appRTDir);
  if (validateWindowsNodeRuntimeRoot(appRTDir, version)) {
    return;
  }

  const archiveFileName = `node-v${version}-win-x64.zip`;
  const zipPath = join(bDir, archiveFileName);

  function buildExpectedMetadata() {
    return (
      JSON.stringify({
        schemaVersion: metadataSchemaVersion,
        nodeVersion: version
      }) + "\n"
    );
  }

  async function downloadArchive() {
    log(`downloading ${url}`);
    const partPath = zipPath + ".part";
    try {
      rmSync(partPath, { force: true });
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      try {
        const response = await fetchFn(url, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(
            `download failed: ${response.status} ${response.statusText}`
          );
        }
        const file = createWriteStream(partPath);
        await pipeline(
          Readable.fromWeb(response.body),
          file,
          { signal: controller.signal }
        );
      } finally {
        clearTimeout(timer);
      }
    } catch (err) {
      rmSync(partPath, { force: true });
      throw err;
    }

    log("verifying SHA-256 of downloaded archive");
    const hash = createHash("sha256");
    await new Promise((resolvePromise, reject) => {
      const stream = createReadStream(partPath);
      stream.on("data", (chunk) => hash.update(chunk));
      stream.on("end", resolvePromise);
      stream.on("error", reject);
    });
    const actual = hash.digest("hex").toLowerCase();
    if (actual !== sha256) {
      rmSync(partPath, { force: true });
      throw new Error(
        `SHA-256 mismatch\n  expected: ${sha256}\n  actual:   ${actual}`
      );
    }
    renameSync(partPath, zipPath);
    log("download complete, SHA-256 verified");
  }

  async function verifyCachedArchive() {
    const hash = createHash("sha256");
    await new Promise((resolvePromise, reject) => {
      const stream = createReadStream(zipPath);
      stream.on("data", (chunk) => hash.update(chunk));
      stream.on("end", resolvePromise);
      stream.on("error", reject);
    });
    const actual = hash.digest("hex").toLowerCase();
    if (actual !== sha256) {
      rmSync(zipPath, { force: true });
      return false;
    }
    return true;
  }

  if (existsSync(zipPath)) {
    log("using cached Node archive, verifying SHA-256");
    const ok = await verifyCachedArchive();
    if (ok) {
      log("cached archive SHA-256 verified");
    } else {
      log("cached archive SHA-256 mismatch, re-downloading");
      await downloadArchive();
    }
  } else {
    await downloadArchive();
  }

  const stagingRoot = mkdtempSync(join(bDir, ".staging-"));
  try {
    const extractDir = join(stagingRoot, "extract");
    mkdirSync(extractDir, { recursive: true });

    log("extracting Node archive");
    const extractedRoot = extractFn({ zipPath, extractDir, version });

    if (!extractedRoot || typeof extractedRoot !== "string") {
      throw new Error("extractImpl must return the extracted root path");
    }
    if (!containsPath(extractDir, extractedRoot)) {
      throw new Error(
        `extracted root ${extractedRoot} escapes extraction directory ${extractDir}`
      );
    }
    if (!isRealDirectory(extractedRoot)) {
      throw new Error(`extracted root is not a directory: ${extractedRoot}`);
    }

    const assembleDir = join(stagingRoot, "app-runtime");
    const assembleNodeDir = join(assembleDir, "node");
    const assembleNodeBinDir = join(assembleNodeDir, "bin");
    mkdirSync(assembleNodeBinDir, { recursive: true });

    for (const name of requiredBinaries) {
      const src = join(extractedRoot, name);
      if (!isRegularFile(src)) {
        throw new Error(
          `required binary missing or not a regular file in archive: ${name}`
        );
      }
      renameSync(src, join(assembleNodeBinDir, name));
    }

    const nodeModulesSrc = join(extractedRoot, "node_modules");
    if (!isRealDirectory(nodeModulesSrc)) {
      throw new Error("node_modules missing or not a real directory in archive");
    }
    if (!containsPath(extractedRoot, nodeModulesSrc)) {
      throw new Error("node_modules escapes the extracted root");
    }
    const npmCliSrc = join(
      extractedRoot,
      "node_modules",
      "npm",
      "bin",
      "npm-cli.js"
    );
    if (!isRegularFile(npmCliSrc)) {
      throw new Error(
        "node_modules/npm/bin/npm-cli.js missing or not a regular file in archive"
      );
    }
    cpSync(nodeModulesSrc, join(assembleNodeBinDir, "node_modules"), {
      recursive: true
    });
    if (
      !isRegularFile(
        join(assembleNodeBinDir, "node_modules", "npm", "bin", "npm-cli.js")
      )
    ) {
      throw new Error("npm-cli.js was not copied to assembled runtime");
    }

    const licenseSrc = join(extractedRoot, "LICENSE");
    if (!isRegularFile(licenseSrc)) {
      throw new Error("LICENSE missing or not a regular file in archive");
    }
    renameSync(licenseSrc, join(assembleNodeDir, "LICENSE"));

    writeFileSync(
      join(assembleNodeDir, metadataFileName),
      buildExpectedMetadata(),
      "utf8"
    );

    if (!validateWindowsNodeRuntimeRoot(assembleDir, version)) {
      throw new Error("assembled Windows Node runtime failed validation");
    }

    rmSync(extractDir, { recursive: true, force: true });

    defaultSwap({
      stagingDir: assembleDir,
      targetDir: appRTDir,
      renameFn: innerRename
    });

    log("Windows Node runtime ready");
    log(`  ${join(appRTDir, "node", "bin", "node.exe")}`);
    log(`  ${join(appRTDir, "node", "bin", "npm.cmd")}`);
    log(`  ${join(appRTDir, "node", metadataFileName)}`);
  } finally {
    rmSync(stagingRoot, { recursive: true, force: true });
  }
}

const scriptPath = resolve(fileURLToPath(import.meta.url));

async function main() {
  let lockContent;
  try {
    lockContent = readFileSync(lockPath, "utf8");
  } catch {
    throw new Error(`windows node runtime lock not found at ${lockPath}`);
  }
  await prepareWindowsNodeRuntime({ buildDir, lockContent });
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  main().catch((err) => {
    log(`ERROR: ${err.message}`);
    process.exit(1);
  });
}
