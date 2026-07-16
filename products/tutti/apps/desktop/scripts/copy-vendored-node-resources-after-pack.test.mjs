import assert from "node:assert/strict";
import { mock, test } from "node:test";

const state = {
  existsSyncReturn: true,
  readdirAppOutDirReturn: [],
  cpSyncCalls: []
};

function resetState() {
  state.existsSyncReturn = true;
  state.readdirAppOutDirReturn = [];
  state.cpSyncCalls = [];
}

mock.module("node:fs", {
  exports: {
    cpSync(src, dst, _opts) {
      state.cpSyncCalls.push({ src, dst });
    },
    existsSync() {
      return state.existsSyncReturn;
    },
    readdirSync(dir) {
      if (dir === "/fake/app-out") {
        return state.readdirAppOutDirReturn;
      }
      return [];
    },
    mkdirSync() {},
    rmSync() {},
    lstatSync() {
      return {
        isSymbolicLink() {
          return false;
        },
        isDirectory() {
          return true;
        }
      };
    }
  }
});

const { default: copyVendoredNodeResourcesAfterPack } =
  await import("./copy-vendored-node-resources-after-pack.mjs");

test("win32 context copies app-runtime into resources", async () => {
  resetState();
  await copyVendoredNodeResourcesAfterPack({
    electronPlatformName: "win32",
    appOutDir: "/fake/app-out"
  });
  const appRtCall = state.cpSyncCalls.find((c) =>
    c.src.includes("app-runtime")
  );
  assert.ok(appRtCall, "app-runtime should be copied on win32");
  assert.ok(
    appRtCall.dst.includes("app-runtime"),
    "destination should include app-runtime"
  );
});

test("linux context does not copy app-runtime", async () => {
  resetState();
  await copyVendoredNodeResourcesAfterPack({
    electronPlatformName: "linux",
    appOutDir: "/fake/app-out"
  });
  const appRtCall = state.cpSyncCalls.find((c) =>
    c.src.includes("app-runtime")
  );
  assert.equal(
    appRtCall,
    undefined,
    "app-runtime should not be copied on linux"
  );
});

test("darwin context does not copy app-runtime", async () => {
  resetState();
  state.readdirAppOutDirReturn = ["Tutti.app"];
  await copyVendoredNodeResourcesAfterPack({
    electronPlatformName: "darwin",
    appOutDir: "/fake/app-out"
  });
  const appRtCall = state.cpSyncCalls.find((c) =>
    c.src.includes("app-runtime")
  );
  assert.equal(
    appRtCall,
    undefined,
    "app-runtime should not be copied on darwin"
  );
});

test("browser-mcp and claude-sdk-sidecar copied on all platforms", async () => {
  for (const platform of ["win32", "linux", "darwin"]) {
    resetState();
    if (platform === "darwin") {
      state.readdirAppOutDirReturn = ["Tutti.app"];
    }
    await copyVendoredNodeResourcesAfterPack({
      electronPlatformName: platform,
      appOutDir: "/fake/app-out"
    });
    const mcpCall = state.cpSyncCalls.find((c) =>
      c.src.includes("browser-mcp")
    );
    const sidecarCall = state.cpSyncCalls.find((c) =>
      c.src.includes("claude-sdk-sidecar")
    );
    assert.ok(mcpCall, `browser-mcp should be copied on ${platform}`);
    assert.ok(
      sidecarCall,
      `claude-sdk-sidecar should be copied on ${platform}`
    );
  }
});

test("win32 copies app-runtime alongside sidecars", async () => {
  resetState();
  await copyVendoredNodeResourcesAfterPack({
    electronPlatformName: "win32",
    appOutDir: "/fake/app-out"
  });
  assert.equal(
    state.cpSyncCalls.length,
    3,
    "should have exactly 3 copies on win32 (2 sidecars + app-runtime)"
  );
});
