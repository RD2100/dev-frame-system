import assert from "node:assert/strict";
import test from "node:test";
import {
  TuttidProtocolError,
  workspaceProtocolErrorCodes
} from "@tutti-os/client-tuttid-ts";
import {
  classifyDesktopErrorCode,
  desktopErrorCodes
} from "./desktopErrors.ts";

test("classifyDesktopErrorCode detects daemon unavailability", () => {
  const error = Object.assign(
    new Error("daemon endpoint is not available yet"),
    {
      code: "ENOENT"
    }
  );

  assert.equal(
    classifyDesktopErrorCode(error),
    desktopErrorCodes.daemonUnavailable
  );
});

test("classifyDesktopErrorCode detects transport timeout", () => {
  const error = Object.assign(
    new Error("Daemon request timed out after 5000ms."),
    {
      code: "ETIMEDOUT"
    }
  );

  assert.equal(
    classifyDesktopErrorCode(error),
    desktopErrorCodes.transportTimeout
  );
});

test("classifyDesktopErrorCode detects connection failures", () => {
  const error = Object.assign(
    new Error("connect ECONNREFUSED 127.0.0.1:4545"),
    {
      code: "ECONNREFUSED"
    }
  );

  assert.equal(
    classifyDesktopErrorCode(error),
    desktopErrorCodes.transportConnectFailed
  );
});

test("classifyDesktopErrorCode detects broken Node linker failures", () => {
  const error = new Error(
    "dyld[66795]: Library not loaded: /opt/homebrew/opt/simdjson/lib/libsimdjson.30.dylib\n" +
      "  Referenced from: /opt/homebrew/Cellar/node@22/22.22.1_1/bin/node"
  );

  assert.equal(
    classifyDesktopErrorCode(error),
    desktopErrorCodes.nodeRuntimeBroken
  );
});

test("classifyDesktopErrorCode preserves daemon protocol codes", () => {
  const error = new TuttidProtocolError({
    code: workspaceProtocolErrorCodes.workspaceNotFound,
    developerMessage: "workspace not found",
    reason: "workspace_not_found",
    statusCode: 404
  });

  assert.equal(
    classifyDesktopErrorCode(error),
    workspaceProtocolErrorCodes.workspaceNotFound
  );
});

test("classifyDesktopErrorCode preserves desktop-local preview codes", () => {
  const error = Object.assign(new Error("preview too large"), {
    code: desktopErrorCodes.previewFileTooLarge
  });

  assert.equal(
    classifyDesktopErrorCode(error),
    desktopErrorCodes.previewFileTooLarge
  );
});
