import assert from "node:assert/strict";
import test from "node:test";
import { workspaceProtocolErrorCodes } from "@tutti-os/client-tuttid-ts";
import { normalizeTuttidError } from "@tutti-os/client-tuttid-ts";
import { DesktopApiError } from "./desktopApiError.ts";

test("DesktopApiError keeps protocol metadata available for normalization", () => {
  const error = new DesktopApiError({
    code: workspaceProtocolErrorCodes.workspaceNotFound,
    correlationId: "corr-1",
    developerMessage: "workspace not found",
    message: "workspace not found",
    params: { workspaceId: "ws-missing" },
    reason: "workspace_not_found",
    retryable: true
  });

  const normalized = normalizeTuttidError(error);

  assert.ok(normalized);
  assert.equal(normalized.code, workspaceProtocolErrorCodes.workspaceNotFound);
  assert.equal(normalized.reason, "workspace_not_found");
  assert.deepEqual(normalized.params, { workspaceId: "ws-missing" });
  assert.equal(normalized.retryable, true);
  assert.equal(normalized.correlationId, "corr-1");
});
