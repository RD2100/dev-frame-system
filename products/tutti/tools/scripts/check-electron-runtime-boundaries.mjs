import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile, readdir } from "node:fs/promises";
import {
  dirname,
  extname,
  join,
  normalize,
  relative,
  resolve,
  sep
} from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const defaultWorkspaceRoot = join(scriptDirectory, "..", "..");
const workspaceRoot = process.env.TUTTI_WORKSPACE_ROOT ?? defaultWorkspaceRoot;
const ts = await loadTypeScriptModule();
const desktopRoot = "apps/desktop";
const runtimeRoots = ["apps/desktop/src/main", "apps/desktop/src/preload"];
const relevantStagedPrefixes = [
  "apps/desktop/electron.vite.config.ts",
  "apps/desktop/src/main/",
  "apps/desktop/src/preload/",
  "apps/desktop/src/shared/",
  "packages/"
];
const ignoredDirectories = new Set([
  ".git",
  ".turbo",
  "dist",
  "node_modules",
  "out"
]);
const runtimeCodeExtensions = new Set([
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".ts",
  ".tsx",
  ".mts",
  ".cts"
]);
const sourceLikeExtensions = new Set([".ts", ".tsx", ".mts", ".cts", ".css"]);
const repoAliases = new Map([
  ["@main/", "apps/desktop/src/main/"],
  ["@preload/", "apps/desktop/src/preload/"],
  ["@renderer/", "apps/desktop/src/renderer/src/"],
  ["@shared/", "apps/desktop/src/shared/"]
]);
const stagedOnly = process.argv.includes("--staged");

const packageRegistry = await loadWorkspacePackageRegistry();
const externalizedPackageExcludes = await loadElectronRuntimeExcludePackages();
const localEdgeCache = new Map();
const packageHazardCache = new Map();
const packageInfoByRoot = Array.from(packageRegistry.values()).sort(
  (left, right) => right.rootPath.length - left.rootPath.length
);
const violations = [];
const reportedViolationKeys = new Set();

if (stagedOnly) {
  const stagedFiles = listStagedFiles();
  const hasRelevantChange = stagedFiles.some((file) =>
    relevantStagedPrefixes.some((prefix) =>
      prefix.endsWith(".ts") ? file === prefix : file.startsWith(prefix)
    )
  );

  if (!hasRelevantChange) {
    console.log(
      "electron runtime boundary check skipped (no relevant staged changes)"
    );
    process.exit(0);
  }
}

const runtimeEntryFiles = await collectRuntimeEntryFiles();
for (const entryFile of runtimeEntryFiles) {
  const visitedLocalFiles = new Set();
  await inspectReachableRuntimeFile(entryFile, visitedLocalFiles);
}

if (violations.length > 0) {
  console.error("Found Electron runtime boundary violations:");
  for (const violation of violations) {
    console.error(
      `- [${violation.rule}] ${violation.file}:${violation.line} ${violation.message}`
    );
    console.error(`  suggestion: ${violation.suggestion}`);
  }

  process.exitCode = 1;
} else {
  console.log("electron runtime boundary check passed");
}

async function collectRuntimeEntryFiles() {
  const files = [];

  for (const runtimeRoot of runtimeRoots) {
    await walkRuntimeRoot(join(workspaceRoot, runtimeRoot), files);
  }

  files.sort();
  return files;
}

async function walkRuntimeRoot(directory, files) {
  const entries = await readdir(directory, { withFileTypes: true });

  for (const entry of entries) {
    const absolutePath = join(directory, entry.name);

    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) {
        await walkRuntimeRoot(absolutePath, files);
      }
      continue;
    }

    if (!entry.isFile()) {
      continue;
    }

    if (!isRuntimeSourceFile(absolutePath)) {
      continue;
    }

    files.push(absolutePath);
  }
}

function isRuntimeSourceFile(absolutePath) {
  const relativePath = toWorkspaceRelative(absolutePath);
  const extension = extname(relativePath);

  if (!runtimeCodeExtensions.has(extension)) {
    return false;
  }

  if (relativePath.endsWith(".d.ts")) {
    return false;
  }

  return !isTestFile(relativePath);
}

function isTestFile(relativePath) {
  return /\.(test|spec)\.[^.]+$/.test(relativePath);
}

async function inspectReachableRuntimeFile(absolutePath, visitedLocalFiles) {
  const normalizedPath = normalize(absolutePath);
  if (visitedLocalFiles.has(normalizedPath)) {
    return;
  }
  visitedLocalFiles.add(normalizedPath);

  const runtimeEdges = await getRuntimeEdges(normalizedPath);
  for (const edge of runtimeEdges) {
    const resolved = resolveImportSpecifier(normalizedPath, edge.specifier);
    if (!resolved) {
      continue;
    }

    if (resolved.kind === "external") {
      if (isReactPackage(resolved.packageName)) {
        reportViolation({
          file: toWorkspaceRelative(normalizedPath),
          line: edge.line,
          message: `runtime import ${edge.specifier} reaches React, which is not allowed in Electron main/preload execution paths`,
          rule: "electron-runtime-ui-leak",
          suggestion:
            "Keep Electron main/preload on non-React modules. Move the needed value into a .ts service/model module and import that instead of a React-facing surface."
        });
      }
      continue;
    }

    if (resolved.kind === "file") {
      if (isTsxFile(resolved.path)) {
        reportViolation({
          file: toWorkspaceRelative(normalizedPath),
          line: edge.line,
          message: `runtime import ${edge.specifier} resolves to ${toWorkspaceRelative(resolved.path)}, which is a .tsx module and not allowed in Electron main/preload execution paths`,
          rule: "electron-runtime-ui-leak",
          suggestion:
            "Move the needed value into a .ts module and import that instead of a .tsx file or a barrel that re-exports React UI."
        });
        continue;
      }

      if (isWorkspaceLocalFile(resolved.path)) {
        await inspectReachableRuntimeFile(resolved.path, visitedLocalFiles);
      }
      continue;
    }

    const hazard = await analyzeWorkspacePackageImport({
      importerPath: normalizedPath,
      line: edge.line,
      specifier: edge.specifier,
      resolvedPackage: resolved
    });

    if (!hazard) {
      continue;
    }

    reportViolation(hazard);
  }
}

async function analyzeWorkspacePackageImport({
  importerPath,
  line,
  specifier,
  resolvedPackage
}) {
  const relativeImporterPath = toWorkspaceRelative(importerPath);
  const trackSourceLike = !externalizedPackageExcludes.has(
    resolvedPackage.packageName
  );
  const cacheKey = `${resolvedPackage.entryPath}:${trackSourceLike ? "source" : "bundled"}`;
  let analysis = packageHazardCache.get(cacheKey);
  if (!analysis) {
    analysis = await analyzeResolvedTargetGraph(resolvedPackage.entryPath, {
      trackSourceLike
    });
    packageHazardCache.set(cacheKey, analysis);
  }

  if (analysis.uiLeakPath) {
    return {
      file: relativeImporterPath,
      line,
      message: `runtime import ${specifier} reaches React UI code via ${formatTrail(
        analysis.uiLeakPath
      )}`,
      rule: "electron-runtime-ui-leak",
      suggestion: buildUiLeakSuggestion({
        packageInfo: resolvedPackage.packageInfo,
        specifier
      })
    };
  }

  if (!analysis.sourceLikePath) {
    return null;
  }

  return {
    file: relativeImporterPath,
    line,
    message: `runtime import ${specifier} is externalized in Electron and resolves to source files via ${formatTrail(
      analysis.sourceLikePath
    )}`,
    rule: "electron-runtime-externalized-source",
    suggestion: buildExternalizedSourceSuggestion({
      packageInfo: resolvedPackage.packageInfo,
      specifier
    })
  };
}

async function analyzeResolvedTargetGraph(entryPath, options) {
  return analyzeFileHazards(normalize(entryPath), options, new Set());
}

async function analyzeFileHazards(filePath, options, activeFiles) {
  const normalizedPath = normalize(filePath);
  const relativePath = toWorkspaceRelative(normalizedPath);
  const extension = extname(relativePath);
  let sourceLikePath =
    options.trackSourceLike && sourceLikeExtensions.has(extension)
      ? [relativePath]
      : null;

  if (isTsxFile(normalizedPath)) {
    return {
      sourceLikePath,
      uiLeakPath: [relativePath]
    };
  }

  if (activeFiles.has(normalizedPath)) {
    return {
      sourceLikePath,
      uiLeakPath: null
    };
  }

  activeFiles.add(normalizedPath);
  const runtimeEdges = await getRuntimeEdges(normalizedPath);

  for (const edge of runtimeEdges) {
    const resolved = resolveImportSpecifier(normalizedPath, edge.specifier);
    if (!resolved) {
      continue;
    }

    if (resolved.kind === "external") {
      if (isReactPackage(resolved.packageName)) {
        activeFiles.delete(normalizedPath);
        return {
          sourceLikePath,
          uiLeakPath: [relativePath, resolved.packageName]
        };
      }
      continue;
    }

    const childPath =
      resolved.kind === "workspace-package"
        ? resolved.entryPath
        : resolved.path;
    const childOptions =
      resolved.kind === "workspace-package"
        ? {
            ...options,
            trackSourceLike: !externalizedPackageExcludes.has(
              resolved.packageName
            )
          }
        : options;
    const childHazards = await analyzeFileHazards(
      childPath,
      childOptions,
      activeFiles
    );

    if (childHazards.uiLeakPath) {
      activeFiles.delete(normalizedPath);
      return {
        sourceLikePath:
          sourceLikePath ??
          prefixTrail(relativePath, childHazards.sourceLikePath),
        uiLeakPath: prefixTrail(relativePath, childHazards.uiLeakPath)
      };
    }

    if (!sourceLikePath && childHazards.sourceLikePath) {
      sourceLikePath = prefixTrail(relativePath, childHazards.sourceLikePath);
    }
  }

  activeFiles.delete(normalizedPath);
  return {
    sourceLikePath,
    uiLeakPath: null
  };
}

function prefixTrail(label, trail) {
  if (!trail) {
    return null;
  }

  if (trail[0] === label) {
    return trail;
  }

  return [label, ...trail];
}

async function getRuntimeEdges(absolutePath) {
  const normalizedPath = normalize(absolutePath);
  if (localEdgeCache.has(normalizedPath)) {
    return localEdgeCache.get(normalizedPath);
  }

  const sourceText = await readFile(normalizedPath, "utf8");
  const scriptKind = normalizedPath.endsWith(".tsx")
    ? ts.ScriptKind.TSX
    : ts.ScriptKind.TS;
  const sourceFile = ts.createSourceFile(
    normalizedPath,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    scriptKind
  );
  const edges = [];

  const visit = (node) => {
    if (ts.isImportDeclaration(node)) {
      const moduleSpecifier = readModuleSpecifier(node.moduleSpecifier);
      if (moduleSpecifier && !node.importClause?.isTypeOnly) {
        edges.push({
          line:
            sourceFile.getLineAndCharacterOfPosition(
              node.moduleSpecifier.getStart()
            ).line + 1,
          specifier: moduleSpecifier
        });
      }
    } else if (ts.isExportDeclaration(node)) {
      const moduleSpecifier = readModuleSpecifier(node.moduleSpecifier);
      if (moduleSpecifier && !node.isTypeOnly) {
        edges.push({
          line:
            sourceFile.getLineAndCharacterOfPosition(
              node.moduleSpecifier.getStart()
            ).line + 1,
          specifier: moduleSpecifier
        });
      }
    } else if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword &&
      node.arguments.length === 1 &&
      ts.isStringLiteralLike(node.arguments[0])
    ) {
      edges.push({
        line:
          sourceFile.getLineAndCharacterOfPosition(node.arguments[0].getStart())
            .line + 1,
        specifier: node.arguments[0].text
      });
    }

    ts.forEachChild(node, visit);
  };

  visit(sourceFile);
  localEdgeCache.set(normalizedPath, edges);
  return edges;
}

function readModuleSpecifier(node) {
  if (!node || !ts.isStringLiteralLike(node)) {
    return null;
  }

  return node.text;
}

function resolveImportSpecifier(importerPath, specifier) {
  if (specifier.startsWith(".")) {
    return resolveRelativeSpecifier(dirname(importerPath), specifier);
  }

  if (specifier.startsWith("/")) {
    return resolveRelativeSpecifier(workspaceRoot, `.${specifier}`);
  }

  for (const [prefix, targetPrefix] of repoAliases.entries()) {
    if (specifier.startsWith(prefix)) {
      return resolveRelativeSpecifier(
        workspaceRoot,
        `./${targetPrefix}${specifier.slice(prefix.length)}`
      );
    }
  }

  if (specifier.startsWith("#")) {
    return resolvePackageImportAlias(importerPath, specifier);
  }

  if (specifier.startsWith("@tutti-os/")) {
    return resolveWorkspacePackageSpecifier(specifier);
  }

  return {
    kind: "external",
    packageName: getBarePackageName(specifier)
  };
}

function resolveRelativeSpecifier(baseDirectory, specifier) {
  const candidate = normalize(resolve(baseDirectory, specifier));
  const resolvedPath = resolveFileCandidate(candidate);
  if (!resolvedPath) {
    return null;
  }

  return {
    kind: "file",
    path: resolvedPath
  };
}

function resolvePackageImportAlias(importerPath, specifier) {
  const packageInfo = getNearestPackageInfo(importerPath);
  if (!packageInfo || !packageInfo.manifest.imports) {
    return null;
  }

  const target = resolveImportsMapEntry(
    packageInfo.manifest.imports,
    specifier
  );
  if (!target) {
    return null;
  }

  return resolveRelativeSpecifier(packageInfo.rootPath, target);
}

function resolveWorkspacePackageSpecifier(specifier) {
  const packageName = getWorkspacePackageName(specifier);
  const packageInfo = packageRegistry.get(packageName);
  if (!packageInfo) {
    return {
      kind: "external",
      packageName
    };
  }

  const subpath = getWorkspacePackageSubpath(specifier);
  const exportTarget = resolvePackageExportTarget(
    packageInfo.manifest.exports,
    subpath
  );
  if (!exportTarget) {
    return null;
  }

  const entryPath = resolveFileCandidate(
    join(packageInfo.rootPath, exportTarget)
  );
  if (!entryPath) {
    return null;
  }

  return {
    entryPath,
    kind: "workspace-package",
    packageInfo,
    packageName
  };
}

function resolvePackageExportTarget(exportsField, subpath) {
  if (!exportsField) {
    return subpath === "." ? "./index.js" : null;
  }

  if (typeof exportsField === "string") {
    return subpath === "." ? exportsField : null;
  }

  const value = exportsField[subpath];
  if (!value) {
    return null;
  }

  return pickConditionalExportTarget(value);
}

function pickConditionalExportTarget(value) {
  if (typeof value === "string") {
    return value;
  }

  if (!value || typeof value !== "object") {
    return null;
  }

  const preferredKeys = ["import", "default", "node"];
  for (const key of preferredKeys) {
    if (typeof value[key] === "string") {
      return value[key];
    }
  }

  for (const candidate of Object.values(value)) {
    const nested = pickConditionalExportTarget(candidate);
    if (nested) {
      return nested;
    }
  }

  return null;
}

function resolveImportsMapEntry(importsField, specifier) {
  if (typeof importsField[specifier] === "string") {
    return importsField[specifier];
  }

  for (const [pattern, rawTarget] of Object.entries(importsField)) {
    if (typeof rawTarget !== "string" || !pattern.includes("*")) {
      continue;
    }

    const [prefix, suffix] = pattern.split("*");
    if (!specifier.startsWith(prefix) || !specifier.endsWith(suffix)) {
      continue;
    }

    const wildcardValue = specifier.slice(
      prefix.length,
      specifier.length - suffix.length
    );
    return rawTarget.replace("*", wildcardValue);
  }

  return null;
}

function resolveFileCandidate(basePath) {
  const candidates = [
    basePath,
    `${basePath}.ts`,
    `${basePath}.tsx`,
    `${basePath}.mts`,
    `${basePath}.cts`,
    `${basePath}.js`,
    `${basePath}.jsx`,
    `${basePath}.mjs`,
    `${basePath}.cjs`,
    `${basePath}.json`,
    join(basePath, "index.ts"),
    join(basePath, "index.tsx"),
    join(basePath, "index.mts"),
    join(basePath, "index.cts"),
    join(basePath, "index.js"),
    join(basePath, "index.jsx"),
    join(basePath, "index.mjs"),
    join(basePath, "index.cjs"),
    join(basePath, "index.json")
  ];

  for (const candidate of candidates) {
    if (ts.sys.fileExists(candidate)) {
      return normalize(candidate);
    }
  }

  return null;
}

async function loadWorkspacePackageRegistry() {
  const packagesRoot = join(workspaceRoot, "packages");
  const packageInfos = [];

  await walkPackageDirectories(packagesRoot, packageInfos);

  return new Map(
    packageInfos
      .filter((packageInfo) =>
        packageInfo.manifest.name?.startsWith("@tutti-os/")
      )
      .map((packageInfo) => [packageInfo.manifest.name, packageInfo])
  );
}

async function walkPackageDirectories(directory, packageInfos) {
  const entries = await readdir(directory, { withFileTypes: true });

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    if (ignoredDirectories.has(entry.name)) {
      continue;
    }

    const absolutePath = join(directory, entry.name);
    const packageJsonPath = join(absolutePath, "package.json");
    if (ts.sys.fileExists(packageJsonPath)) {
      const manifest = JSON.parse(await readFile(packageJsonPath, "utf8"));
      packageInfos.push({
        manifest,
        packageJsonPath,
        rootPath: absolutePath
      });
    }

    await walkPackageDirectories(absolutePath, packageInfos);
  }
}

async function loadElectronRuntimeExcludePackages() {
  const configPath = join(
    workspaceRoot,
    desktopRoot,
    "electron.vite.config.ts"
  );
  const sourceText = await readFile(configPath, "utf8");
  const sourceFile = ts.createSourceFile(
    configPath,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS
  );
  const excludes = new Set();

  const visit = (node) => {
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === "externalizeDepsPlugin" &&
      node.arguments.length > 0 &&
      ts.isObjectLiteralExpression(node.arguments[0])
    ) {
      const optionsObject = node.arguments[0];
      for (const property of optionsObject.properties) {
        if (
          ts.isPropertyAssignment(property) &&
          getPropertyName(property.name) === "exclude" &&
          ts.isArrayLiteralExpression(property.initializer)
        ) {
          for (const element of property.initializer.elements) {
            if (ts.isStringLiteralLike(element)) {
              excludes.add(element.text);
            }
          }
        }
      }
    }

    ts.forEachChild(node, visit);
  };

  visit(sourceFile);
  return excludes;
}

function getPropertyName(nameNode) {
  if (!nameNode) {
    return null;
  }

  if (
    ts.isIdentifier(nameNode) ||
    ts.isStringLiteralLike(nameNode) ||
    ts.isNumericLiteral(nameNode)
  ) {
    return nameNode.text;
  }

  return null;
}

function getNearestPackageInfo(filePath) {
  const normalizedPath = normalize(filePath);
  return (
    packageInfoByRoot.find((packageInfo) =>
      normalizedPath.startsWith(`${normalize(packageInfo.rootPath)}${sep}`)
    ) ?? null
  );
}

function getWorkspacePackageName(specifier) {
  const segments = specifier.split("/");
  return `${segments[0]}/${segments[1]}`;
}

function getWorkspacePackageSubpath(specifier) {
  const segments = specifier.split("/");
  if (segments.length <= 2) {
    return ".";
  }

  return `./${segments.slice(2).join("/")}`;
}

function getBarePackageName(specifier) {
  if (specifier.startsWith("@")) {
    const [scope, name] = specifier.split("/");
    return `${scope}/${name}`;
  }

  return specifier.split("/")[0];
}

function isReactPackage(packageName) {
  return packageName === "react" || packageName === "react-dom";
}

function isTsxFile(filePath) {
  return extname(filePath) === ".tsx";
}

function isWorkspaceLocalFile(filePath) {
  const relativePath = toWorkspaceRelative(filePath);
  return (
    !relativePath.startsWith("..") &&
    !relativePath.includes("/node_modules/") &&
    !ignoredDirectories.has(relativePath.split("/")[0] ?? "")
  );
}

function buildUiLeakSuggestion({ packageInfo, specifier }) {
  const candidateSubpaths = listNonUiExportSubpaths(packageInfo);
  if (specifier === packageInfo.manifest.name && candidateSubpaths.length > 0) {
    return `Import a non-UI subpath instead of the root barrel. Candidate exports: ${candidateSubpaths
      .map((subpath) => `${packageInfo.manifest.name}${subpath.slice(1)}`)
      .join(
        ", "
      )}. If the needed value is still only exposed from the root barrel, split it into a dedicated .ts service/model subpath.`;
  }

  return "Keep Electron main/preload on non-React modules. Import a non-UI subpath, or split service/model exports into a dedicated .ts barrel that does not re-export React UI.";
}

function buildExternalizedSourceSuggestion({ packageInfo, specifier }) {
  const candidateSubpaths = listNonUiExportSubpaths(packageInfo);
  const baseSuggestion = `Either add ${packageInfo.manifest.name} to apps/desktop/electron.vite.config.ts externalizeDepsPlugin({ exclude }), or export a JS runtime entry instead of raw source files for Electron runtime consumers.`;

  if (specifier === packageInfo.manifest.name && candidateSubpaths.length > 0) {
    return `${baseSuggestion} If only a subset is needed, prefer a narrower subpath such as ${candidateSubpaths
      .map((subpath) => `${packageInfo.manifest.name}${subpath.slice(1)}`)
      .join(", ")}.`;
  }

  return baseSuggestion;
}

function listNonUiExportSubpaths(packageInfo) {
  const exportsField = packageInfo.manifest.exports;
  if (!exportsField || typeof exportsField !== "object") {
    return [];
  }

  return Object.keys(exportsField).filter((subpath) => {
    if (subpath === ".") {
      return false;
    }

    return !(
      subpath.includes("components") ||
      subpath.includes("icons") ||
      subpath.includes("styles") ||
      subpath.endsWith(".css")
    );
  });
}

function formatTrail(trail) {
  return trail.join(" -> ");
}

function reportViolation(violation) {
  const key = `${violation.rule}:${violation.file}:${violation.line}:${violation.message}`;
  if (reportedViolationKeys.has(key)) {
    return;
  }

  reportedViolationKeys.add(key);
  violations.push(violation);
}

function listStagedFiles() {
  const output = execFileSync(
    "git",
    ["diff", "--cached", "--name-only", "--diff-filter=ACMR"],
    {
      cwd: workspaceRoot,
      encoding: "utf8"
    }
  );

  return output
    .split("\n")
    .map((file) => file.trim())
    .filter(Boolean);
}

function toWorkspaceRelative(absolutePath) {
  return normalizeToPosix(relative(workspaceRoot, absolutePath));
}

function normalizeToPosix(path) {
  return normalize(path).split(sep).join("/");
}

async function loadTypeScriptModule() {
  const candidatePaths = [
    join(defaultWorkspaceRoot, "node_modules/typescript/lib/typescript.js"),
    join(
      defaultWorkspaceRoot,
      "apps/desktop/node_modules/typescript/lib/typescript.js"
    ),
    join(
      defaultWorkspaceRoot,
      "packages/clients/tuttid-ts/node_modules/typescript/lib/typescript.js"
    ),
    join(
      defaultWorkspaceRoot,
      "packages/workbench/snapshot/node_modules/typescript/lib/typescript.js"
    ),
    join(
      defaultWorkspaceRoot,
      "packages/workbench/surface/node_modules/typescript/lib/typescript.js"
    ),
    join(
      defaultWorkspaceRoot,
      "packages/workspace/file-manager/node_modules/typescript/lib/typescript.js"
    )
  ];

  for (const candidatePath of candidatePaths) {
    if (!existsSync(candidatePath)) {
      continue;
    }

    const module = await import(pathToFileURL(candidatePath).href);
    return module.default ?? module;
  }

  throw new Error(
    "Unable to locate a TypeScript runtime for check-electron-runtime-boundaries.mjs"
  );
}
