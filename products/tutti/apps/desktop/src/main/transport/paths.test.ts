import assert from "node:assert/strict";
import test from "node:test";
import {
  resolveDesktopBusinessEventStreamUrl,
  resolveDesktopTerminalStreamUrl,
  type DesktopDaemonEndpoint
} from "./paths.ts";

const endpoint: DesktopDaemonEndpoint = {
  accessToken: "desktop-token",
  boundAddr: "127.0.0.1:4545",
  listenerInfoPath: "/tmp/tuttid.listener.json",
  pidPath: "/tmp/tuttid.pid",
  requestedAddr: "127.0.0.1:0"
};

test("resolveDesktopTerminalStreamUrl preserves terminal websocket semantics", () => {
  assert.equal(
    resolveDesktopTerminalStreamUrl(endpoint, {
      afterSeq: 42,
      sessionId: "term-1",
      workspaceId: "workspace-1"
    }),
    "ws://127.0.0.1:4545/v1/workspaces/workspace-1/terminals/term-1/ws?access_token=desktop-token&afterSeq=42"
  );
});

test("resolveDesktopBusinessEventStreamUrl uses the managed business event route", () => {
  assert.equal(
    resolveDesktopBusinessEventStreamUrl(endpoint),
    "ws://127.0.0.1:4545/v1/events/ws?access_token=desktop-token"
  );
});
