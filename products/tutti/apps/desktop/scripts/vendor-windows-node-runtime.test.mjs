import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import {
  parseLock,
  prepareWindowsNodeRuntime,
  syncVersionModule,
  validateWindowsNodeRuntimeRoot
} from "./vendor-windows-node-runtime.mjs";

const realFetch = globalThis.fetch;
globalThis.fetch = () => {
  throw new Error("unit tests must not call globalThis.fetch");
};

const validSHA =
  "cc5149eabd53779ce1e7bdc5401643622d0c7e6800ade18928a767e940bb0e62";

const lockFixture = {
  schemaVersion: "tutti.windows-node-runtime-lock.v1",
  node: {
    version: "24.15.0",
    url: "https://nodejs.org/download/release/v24.15.0/node-v24.15.0-win-x64.zip",
    sha256: validSHA
  }
};

const lockJSON = JSON.stringify(lockFixture);

const metadataFixture =
  JSON.stringify({
    schemaVersion: "tutti.windows-node-runtime-metadata.v1",
    nodeVersion: "24.15.0"
  }) + "\n";

function writeValidRuntime(root) {
  const nodeBinDir = join(root, "node", "bin");
  mkdirSync(nodeBinDir, { recursive: true });
  writeFileSync(join(nodeBinDir, "node.exe"), "stub");
  writeFileSync(join(nodeBinDir, "npm.cmd"), "stub");
  writeFileSync(join(nodeBinDir, "npx.cmd"), "stub");
  const npmCliDir = join(nodeBinDir, "node_modules", "npm", "bin");
  mkdirSync(npmCliDir, { recursive: true });
  writeFileSync(join(npmCliDir, "npm-cli.js"), "stub");
  writeFileSync(join(root, "node", "LICENSE"), "stub");
  writeFileSync(
    join(root, "node", ".tutti-runtime-metadata.json"),
    metadataFixture
  );
}

function writeWrongVersionRuntime(root) {
  writeValidRuntime(root);
  writeFileSync(
    join(root, "node", ".tutti-runtime-metadata.json"),
    JSON.stringify({
      schemaVersion: "tutti.windows-node-runtime-metadata.v1",
      nodeVersion: "99.99.99"
    }) + "\n"
  );
}

function sentinelWrite(root, name, content) {
  const p = join(root, name);
  writeFileSync(p, content);
  return {
    path: p,
    content,
    hash: createHash("sha256").update(content).digest("hex")
  };
}

function sentinelVerify(sentinel) {
  if (!existsSync(sentinel.path)) return false;
  const current = readFileSync(sentinel.path, "utf8");
  const currentHash = createHash("sha256").update(current).digest("hex");
  return currentHash === sentinel.hash;
}

function makeFakeExtractTree(extractDir, version) {
  const root = join(extractDir, `node-v${version}-win-x64`);
  mkdirSync(join(root, "node_modules", "npm", "bin"), { recursive: true });
  writeFileSync(join(root, "node.exe"), "fake-exe");
  writeFileSync(join(root, "npm.cmd"), "fake-cmd");
  writeFileSync(join(root, "npx.cmd"), "fake-cmd");
  writeFileSync(
    join(root, "node_modules", "npm", "bin", "npm-cli.js"),
    "fake-cli"
  );
  writeFileSync(join(root, "LICENSE"), "fake-license");
  return root;
}

function fakeFetchWithBody(bodyStr) {
  return () => ({
    ok: true,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(bodyStr));
        controller.close();
      }
    })
  });
}

const { ReadableStream, TextEncoder } = globalThis;

// ---- parseLock ----

test("parseLock parses a valid lock", () => {
  const got = parseLock(lockJSON);
  assert.equal(got.version, "24.15.0");
  assert.equal(got.sha256, validSHA);
});

test("parseLock rejects non-JSON", () => {
  assert.throws(() => parseLock("not json"), {
    message: "windows node runtime lock is not valid JSON"
  });
});

test("parseLock rejects wrong schema version", () => {
  const bad = JSON.stringify({ ...lockFixture, schemaVersion: "wrong.v1" });
  assert.throws(() => parseLock(bad), {
    message:
      "windows node runtime lock schemaVersion must be tutti.windows-node-runtime-lock.v1"
  });
});

test("parseLock rejects missing node entry", () => {
  assert.throws(
    () =>
      parseLock(
        JSON.stringify({ schemaVersion: "tutti.windows-node-runtime-lock.v1" })
      ),
    { message: "windows node runtime lock is missing the node entry" }
  );
});

test("parseLock rejects non-semantic version", () => {
  const bad = JSON.stringify({
    ...lockFixture,
    node: { ...lockFixture.node, version: "v24.15.0" }
  });
  assert.throws(() => parseLock(bad), {
    message: /node\.version must be a semantic version/
  });
});

test("parseLock rejects non-https URL", () => {
  const bad = JSON.stringify({
    ...lockFixture,
    node: {
      ...lockFixture.node,
      url: "http://nodejs.org/download/release/v24.15.0/node-v24.15.0-win-x64.zip"
    }
  });
  assert.throws(() => parseLock(bad), {
    message: /node\.url must use https/
  });
});

test("parseLock rejects non-nodejs.org host", () => {
  const bad = JSON.stringify({
    ...lockFixture,
    node: {
      ...lockFixture.node,
      url: "https://example.com/download/node-v24.15.0-win-x64.zip"
    }
  });
  assert.throws(() => parseLock(bad), {
    message: /node\.url host must be nodejs\.org/
  });
});

test("parseLock rejects URL with mismatched filename", () => {
  const bad = JSON.stringify({
    ...lockFixture,
    node: {
      ...lockFixture.node,
      url: "https://nodejs.org/download/release/v24.15.0/node-v99.99.99-win-x64.zip"
    }
  });
  assert.throws(() => parseLock(bad), {
    message: /node\.url must end with/
  });
});

test("parseLock rejects invalid URL format", () => {
  const bad = JSON.stringify({
    ...lockFixture,
    node: { ...lockFixture.node, url: "not-a-url" }
  });
  assert.throws(() => parseLock(bad), {
    message: /not a valid URL/
  });
});

test("parseLock rejects non-hex SHA", () => {
  const bad = JSON.stringify({
    ...lockFixture,
    node: { ...lockFixture.node, sha256: "g".repeat(64) }
  });
  assert.throws(() => parseLock(bad), {
    message: /64 hex characters/
  });
});

test("parseLock rejects wrong-length SHA", () => {
  const bad = JSON.stringify({
    ...lockFixture,
    node: { ...lockFixture.node, sha256: "a".repeat(63) }
  });
  assert.throws(() => parseLock(bad), {
    message: /64 hex characters/
  });
});

// ---- validateWindowsNodeRuntimeRoot ----

test("validateWindowsNodeRuntimeRoot rejects non-string", () => {
  assert.equal(validateWindowsNodeRuntimeRoot(null), false);
  assert.equal(validateWindowsNodeRuntimeRoot(undefined), false);
  assert.equal(validateWindowsNodeRuntimeRoot(123), false);
});

test("validateWindowsNodeRuntimeRoot rejects empty root", () => {
  const root = mkdtempSync(join(tmpdir(), "tutti-validate-"));
  try {
    assert.equal(validateWindowsNodeRuntimeRoot(root), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("validateWindowsNodeRuntimeRoot accepts a valid root", () => {
  const root = mkdtempSync(join(tmpdir(), "tutti-validate-"));
  try {
    writeValidRuntime(root);
    assert.equal(validateWindowsNodeRuntimeRoot(root), true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("validateWindowsNodeRuntimeRoot rejects version mismatch", () => {
  const root = mkdtempSync(join(tmpdir(), "tutti-validate-"));
  try {
    writeValidRuntime(root);
    assert.equal(validateWindowsNodeRuntimeRoot(root, "99.99.99"), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("validateWindowsNodeRuntimeRoot rejects directory as node.exe", () => {
  const root = mkdtempSync(join(tmpdir(), "tutti-validate-"));
  try {
    writeValidRuntime(root);
    rmSync(join(root, "node", "bin", "node.exe"), { force: true });
    mkdirSync(join(root, "node", "bin", "node.exe"), { recursive: true });
    assert.equal(validateWindowsNodeRuntimeRoot(root), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("validateWindowsNodeRuntimeRoot rejects directory as npm-cli.js", () => {
  const root = mkdtempSync(join(tmpdir(), "tutti-validate-"));
  try {
    writeValidRuntime(root);
    rmSync(
      join(root, "node", "bin", "node_modules", "npm", "bin", "npm-cli.js"),
      { force: true }
    );
    mkdirSync(
      join(root, "node", "bin", "node_modules", "npm", "bin", "npm-cli.js"),
      { recursive: true }
    );
    assert.equal(validateWindowsNodeRuntimeRoot(root), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("validateWindowsNodeRuntimeRoot rejects directory as LICENSE", () => {
  const root = mkdtempSync(join(tmpdir(), "tutti-validate-"));
  try {
    writeValidRuntime(root);
    rmSync(join(root, "node", "LICENSE"), { force: true });
    mkdirSync(join(root, "node", "LICENSE"), { recursive: true });
    assert.equal(validateWindowsNodeRuntimeRoot(root), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("validateWindowsNodeRuntimeRoot rejects missing metadata", () => {
  const root = mkdtempSync(join(tmpdir(), "tutti-validate-"));
  try {
    writeValidRuntime(root);
    rmSync(join(root, "node", ".tutti-runtime-metadata.json"), {
      force: true
    });
    assert.equal(validateWindowsNodeRuntimeRoot(root), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

// ---- syncVersionModule ----

test("syncVersionModule renders correct content", () => {
  const dir = mkdtempSync(join(tmpdir(), "tutti-sync-"));
  try {
    const p = join(dir, "windowsNodeRuntimeVersion.ts");
    syncVersionModule("99.88.77", p);
    assert.ok(existsSync(p));
    const content = readFileSync(p, "utf8");
    assert.ok(
      content.includes('pinnedWindowsNodeVersion = "99.88.77"'),
      `content: ${content}`
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("syncVersionModule is idempotent", () => {
  const dir = mkdtempSync(join(tmpdir(), "tutti-sync-"));
  try {
    const p = join(dir, "windowsNodeRuntimeVersion.ts");
    const content = [
      "// Generated from config/tutti.windows-node-runtime.lock.json by",
      "// apps/desktop/scripts/vendor-windows-node-runtime.mjs.",
      "// Single source of expected Windows Node runtime identity",
      "// used by isWindowsNodeRuntimeRootValid at desktop startup.",
      'export const pinnedWindowsNodeVersion = "99.88.77";',
      ""
    ].join("\n");
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, content, "utf8");

    syncVersionModule("99.88.77", p);
    const after = readFileSync(p, "utf8");
    assert.equal(after, content);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ---- prepareWindowsNodeRuntime offline ----

test("prepareWindowsNodeRuntime skips when valid runtime exists", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    writeValidRuntime(join(buildDir, "app-runtime"));
    let fetchCalled = false;
    await prepareWindowsNodeRuntime({
      buildDir,
      lockContent: lockJSON,
      fetchImpl() {
        fetchCalled = true;
        return { ok: false };
      }
    });
    assert.equal(fetchCalled, false);
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("corrupt cached archive replaced and assembled in one call", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    writeFileSync(join(buildDir, "node-v24.15.0-win-x64.zip"), "corrupt");

    const bodyContent = "valid-zip-for-test";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await prepareWindowsNodeRuntime({
      buildDir,
      lockContent: lockWithHash,
      fetchImpl: fakeFetchWithBody(bodyContent),
      extractImpl({ extractDir, version }) {
        return makeFakeExtractTree(extractDir, version);
      }
    });

    assert.equal(
      validateWindowsNodeRuntimeRoot(join(buildDir, "app-runtime"), "24.15.0"),
      true
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("stalled body times out, .part removed, prior runtime sentinel intact", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const appRTDir = join(buildDir, "app-runtime");
    writeWrongVersionRuntime(appRTDir);
    const sentinel = sentinelWrite(appRTDir, ".sentinel", "before-" + Date.now());

    await assert.rejects(
      prepareWindowsNodeRuntime({
        buildDir,
        lockContent: lockJSON,
        downloadTimeoutMs: 50,
        fetchImpl(_url, opts) {
          assert.ok(opts.signal);
          return {
            ok: true,
            body: new ReadableStream({
              pull() {
                return new Promise(() => {});
              }
            })
          };
        }
      }),
      /aborted|AbortError/i
    );

    assert.equal(
      existsSync(join(buildDir, "node-v24.15.0-win-x64.zip.part")),
      false,
      ".part must be removed"
    );
    assert.equal(sentinelVerify(sentinel), true, "sentinel unchanged");
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("extraction failure preserves runtime with sentinel", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const appRTDir = join(buildDir, "app-runtime");
    writeWrongVersionRuntime(appRTDir);
    const sentinel = sentinelWrite(appRTDir, ".sentinel", "before-" + Date.now());

    const bodyContent = "archive-content";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await assert.rejects(
      prepareWindowsNodeRuntime({
        buildDir,
        lockContent: lockWithHash,
        fetchImpl: fakeFetchWithBody(bodyContent),
        extractImpl() {
          throw new Error("simulated extraction failure");
        }
      }),
      /simulated extraction failure/
    );

    assert.equal(sentinelVerify(sentinel), true, "sentinel unchanged");
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("production rollback restores old runtime when second rename fails", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const appRTDir = join(buildDir, "app-runtime");
    writeWrongVersionRuntime(appRTDir);
    const sentinel = sentinelWrite(appRTDir, ".sentinel", "before-" + Date.now());

    const bodyContent = "replacement-body";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    let callCount = 0;
    const mockRename = (src, dst) => {
      callCount++;
      if (callCount === 2) {
        throw new Error("simulated second rename failure");
      }
      renameSync(src, dst);
    };

    await assert.rejects(
      prepareWindowsNodeRuntime({
        buildDir,
        lockContent: lockWithHash,
        fetchImpl: fakeFetchWithBody(bodyContent),
        extractImpl({ extractDir, version }) {
          return makeFakeExtractTree(extractDir, version);
        },
        renameImpl: mockRename
      }),
      /simulated second rename failure/
    );

    assert.ok(callCount >= 3, `expected >=3 rename calls (backup + fail + restore), got ${callCount}`);
    assert.equal(sentinelVerify(sentinel), true, "old sentinel restored at app-runtime");

    const backupDir = join(buildDir, ".app-runtime-backup");
    assert.equal(existsSync(backupDir), false, "backup cleaned up after rollback");
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("stranded backup recovered when app-runtime absent", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const ancestor = join(buildDir, "build");
    mkdirSync(ancestor, { recursive: true });
    const backupDir = join(ancestor, ".app-runtime-backup");
    writeValidRuntime(backupDir);

    const bodyContent = "test-body";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await prepareWindowsNodeRuntime({
      buildDir: ancestor,
      lockContent: lockWithHash,
      fetchImpl: fakeFetchWithBody(bodyContent),
      extractImpl({ extractDir, version }) {
        return makeFakeExtractTree(extractDir, version);
      }
    });

    assert.equal(existsSync(backupDir), false, "backup cleaned up");
    assert.equal(
      validateWindowsNodeRuntimeRoot(join(ancestor, "app-runtime"), "24.15.0"),
      true,
      "backup recovered"
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("successful assembly asserts regular files and metadata", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const bodyContent = "full-test-content";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await prepareWindowsNodeRuntime({
      buildDir,
      lockContent: lockWithHash,
      fetchImpl: fakeFetchWithBody(bodyContent),
      extractImpl({ extractDir, version }) {
        return makeFakeExtractTree(extractDir, version);
      }
    });

    const appRTDir = join(buildDir, "app-runtime");
    assert.equal(validateWindowsNodeRuntimeRoot(appRTDir, "24.15.0"), true);

    const meta = JSON.parse(
      readFileSync(
        join(appRTDir, "node", ".tutti-runtime-metadata.json"),
        "utf8"
      )
    );
    assert.equal(meta.schemaVersion, "tutti.windows-node-runtime-metadata.v1");
    assert.equal(meta.nodeVersion, "24.15.0");

    for (const name of ["node.exe", "npm.cmd", "npx.cmd"]) {
      const p = join(appRTDir, "node", "bin", name);
      assert.ok(existsSync(p), `${name} should exist`);
      assert.ok(statSync(p).isFile(), `${name} should be a regular file`);
    }
    const npmCliPath = join(
      appRTDir,
      "node",
      "bin",
      "node_modules",
      "npm",
      "bin",
      "npm-cli.js"
    );
    assert.ok(existsSync(npmCliPath), "npm-cli.js should exist");
    assert.ok(statSync(npmCliPath).isFile(), "npm-cli.js should be a regular file");
    assert.ok(
      statSync(join(appRTDir, "node", "LICENSE")).isFile(),
      "LICENSE should be a regular file"
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("extraction escape rejected", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const bodyContent = "body";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await assert.rejects(
      prepareWindowsNodeRuntime({
        buildDir,
        lockContent: lockWithHash,
        fetchImpl: fakeFetchWithBody(bodyContent),
        extractImpl({ extractDir }) {
          return join(tmpdir(), "escaped-outside-staging");
        }
      }),
      /escapes extraction directory/
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("extraction non-directory rejected", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const bodyContent = "body";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await assert.rejects(
      prepareWindowsNodeRuntime({
        buildDir,
        lockContent: lockWithHash,
        fetchImpl: fakeFetchWithBody(bodyContent),
        extractImpl({ extractDir }) {
          const f = join(extractDir, "not-a-dir");
          writeFileSync(f, "x");
          return f;
        }
      }),
      /not a directory/
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("extraction exact parent of extractDir is rejected", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const bodyContent = "body";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await assert.rejects(
      prepareWindowsNodeRuntime({
        buildDir,
        lockContent: lockWithHash,
        fetchImpl: fakeFetchWithBody(bodyContent),
        extractImpl({ extractDir }) {
          return join(extractDir, "..");
        }
      }),
      /escapes extraction directory/
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("extraction symlink pointing outside staging is rejected", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const bodyContent = "body";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    const externalDir = join(buildDir, "outside");
    mkdirSync(externalDir, { recursive: true });
    writeFileSync(join(externalDir, "sentinel"), "outside");

    const canSymlink = (() => {
      try {
        const testDir = mkdtempSync(join(tmpdir(), "tutti-link-test-"));
        const testLink = join(testDir, "link");
        symlinkSync(testDir, testLink, "junction");
        rmSync(testDir, { recursive: true, force: true });
        return true;
      } catch {
        return false;
      }
    })();

    if (!canSymlink) {
      return;
    }

    await assert.rejects(
      prepareWindowsNodeRuntime({
        buildDir,
        lockContent: lockWithHash,
        fetchImpl: fakeFetchWithBody(bodyContent),
        extractImpl({ extractDir }) {
          const linkPath = join(extractDir, "fake-root");
          symlinkSync(externalDir, linkPath, "junction");
          return linkPath;
        }
      }),
      /escapes extraction directory/
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

test("contained child directory named ..runtime is accepted", async () => {
  const buildDir = mkdtempSync(join(tmpdir(), "tutti-build-"));
  try {
    const bodyContent = "body";
    const bodyHash = createHash("sha256").update(bodyContent).digest("hex");
    const lockWithHash = JSON.stringify({
      ...lockFixture,
      node: { ...lockFixture.node, sha256: bodyHash }
    });

    await prepareWindowsNodeRuntime({
      buildDir,
      lockContent: lockWithHash,
      fetchImpl: fakeFetchWithBody(bodyContent),
      extractImpl({ extractDir, version }) {
        const root = join(extractDir, "..runtime", `node-v${version}-win-x64`);
        mkdirSync(join(root, "node_modules", "npm", "bin"), { recursive: true });
        writeFileSync(join(root, "node.exe"), "fake-exe");
        writeFileSync(join(root, "npm.cmd"), "fake-cmd");
        writeFileSync(join(root, "npx.cmd"), "fake-cmd");
        writeFileSync(join(root, "node_modules", "npm", "bin", "npm-cli.js"), "fake-cli");
        writeFileSync(join(root, "LICENSE"), "fake-license");
        return root;
      }
    });

    assert.equal(
      validateWindowsNodeRuntimeRoot(join(buildDir, "app-runtime"), "24.15.0"),
      true,
      "..runtime child directory should be accepted as contained"
    );
  } finally {
    rmSync(buildDir, { recursive: true, force: true });
  }
});

process.on("beforeExit", () => {
  globalThis.fetch = realFetch;
});
