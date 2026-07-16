import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import {
  WorkspaceAppFrontendLogWriter,
  WorkspaceAppGuestLogRateLimiter,
  formatWorkspaceAppWebLogLine,
  normalizeWorkspaceAppDiagnosticLogRecord,
  resolveWorkspaceAppWebLogPath
} from "./workspaceAppFrontendLogging.ts";
import { workspaceAppScopeSegment } from "../host/workspaceAppFolderPaths.ts";

test("formats workspace app web log lines with injected context", () => {
  const line = formatWorkspaceAppWebLogLine(
    {
      event: "page.loaded",
      level: "info",
      details: { route: "/home" }
    },
    {
      appID: "demo-app",
      workspaceID: "workspace-1"
    },
    "session-123"
  );

  assert.match(line, /^time=/);
  assert.match(line, /level=info/);
  assert.match(line, /session_id="session-123"/);
  assert.match(line, /workspace_id="workspace-1"/);
  assert.match(line, /app_id="demo-app"/);
  assert.match(line, /web_event="page.loaded"/);
  assert.match(line, /web_details=\{"route":"\/home"\}/);
  assert.match(line, /\n$/);
});

test("resolves workspace app web log path under app logs dir", () => {
  const path = resolveWorkspaceAppWebLogPath("/tmp/tutti-state", {
    appID: "demo-app",
    workspaceID: "workspace-1"
  });

  assert.equal(
    path,
    join(
      "/tmp/tutti-state",
      "apps",
      "installations",
      "demo-app",
      workspaceAppScopeSegment("workspace-1", "demo-app"),
      "logs",
      "web.log"
    )
  );
});

test("workspace app frontend log writer appends to web.log", async () => {
  const root = await mkdtemp(join(tmpdir(), "tutti-web-log-"));

  const writer = new WorkspaceAppFrontendLogWriter(
    root,
    "session-abc",
    new WorkspaceAppGuestLogRateLimiter()
  );

  writer.write(
    1,
    { appID: "demo-app", workspaceID: "workspace-1" },
    { event: "page.loaded", details: { ok: true } }
  );
  writer.write(
    1,
    { appID: "demo-app", workspaceID: "workspace-1" },
    { event: "page.ready" }
  );

  const logPath = resolveWorkspaceAppWebLogPath(root, {
    appID: "demo-app",
    workspaceID: "workspace-1"
  });
  const content = await readWorkspaceAppWebLogUntil(logPath, [
    /web_event="page.loaded"/,
    /web_event="page.ready"/
  ]);

  assert.match(content, /web_event="page.loaded"/);
  assert.match(content, /web_event="page.ready"/);

  await rm(root, { recursive: true, force: true });
});

test("workspace app guest log rate limiter silently drops excess entries", () => {
  const limiter = new WorkspaceAppGuestLogRateLimiter();
  let allowed = 0;

  for (let index = 0; index < 60; index += 1) {
    if (limiter.allow(42)) {
      allowed += 1;
    }
  }

  assert.equal(allowed, 50);
});

test("normalizes workspace app preload diagnostic payloads", () => {
  assert.deepEqual(
    normalizeWorkspaceAppDiagnosticLogRecord({
      event: "get-context-failed",
      details: { message: "invalid workspace app context" }
    }),
    {
      event: "get-context-failed",
      level: "warn",
      details: { message: "invalid workspace app context" },
      webSource: "preload"
    }
  );
  assert.equal(
    normalizeWorkspaceAppDiagnosticLogRecord({ details: { message: "x" } }),
    null
  );
});

async function readWorkspaceAppWebLogUntil(
  logPath: string,
  patterns: RegExp[]
): Promise<string> {
  const deadline = Date.now() + 1_000;
  let lastContent = "";
  let lastError: unknown;

  while (Date.now() < deadline) {
    try {
      lastContent = await readFile(logPath, "utf8");
      if (patterns.every((pattern) => pattern.test(lastContent))) {
        return lastContent;
      }
    } catch (error) {
      lastError = error;
    }

    await new Promise((resolve) => setTimeout(resolve, 10));
  }

  if (lastContent) {
    return lastContent;
  }
  throw lastError;
}
