import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  mapWorkspaceAppRuntimeStatus,
  resolveWorkspaceAppStatusPresentation
} from "./statusMapping.ts";

describe("workspace app status mapping", () => {
  it("maps host-neutral aliases into the V1 runtime statuses", () => {
    assert.equal(mapWorkspaceAppRuntimeStatus("launching"), "starting");
    assert.equal(mapWorkspaceAppRuntimeStatus("installing"), "installing");
    assert.equal(
      mapWorkspaceAppRuntimeStatus("downloading_runtime"),
      "preparing"
    );
    assert.equal(mapWorkspaceAppRuntimeStatus("active"), "running");
    assert.equal(mapWorkspaceAppRuntimeStatus("crashed"), "failed");
    assert.equal(mapWorkspaceAppRuntimeStatus("terminating"), "stopping");
    assert.equal(mapWorkspaceAppRuntimeStatus("stale"), "unavailable");
    assert.equal(
      mapWorkspaceAppRuntimeStatus("runner_unavailable"),
      "unavailable"
    );
    assert.equal(
      mapWorkspaceAppRuntimeStatus("sandbox_unavailable"),
      "unavailable"
    );
    assert.equal(mapWorkspaceAppRuntimeStatus("unreachable"), "unavailable");
    assert.equal(mapWorkspaceAppRuntimeStatus("unknown"), "idle");
  });

  it("resolves view presentation for busy and failed states", () => {
    assert.deepEqual(resolveWorkspaceAppStatusPresentation("installing"), {
      labelKey: "status.installing",
      pulse: true,
      tone: "blue"
    });
    assert.deepEqual(resolveWorkspaceAppStatusPresentation("starting"), {
      labelKey: "status.starting",
      pulse: true,
      tone: "blue"
    });
    assert.deepEqual(resolveWorkspaceAppStatusPresentation("preparing"), {
      labelKey: "status.preparing",
      pulse: true,
      tone: "blue"
    });
    assert.deepEqual(resolveWorkspaceAppStatusPresentation("failed"), {
      labelKey: "status.failed",
      pulse: false,
      tone: "red"
    });
    assert.deepEqual(resolveWorkspaceAppStatusPresentation("idle"), {
      labelKey: "actions.openApp",
      pulse: false,
      tone: "neutral"
    });
    assert.deepEqual(resolveWorkspaceAppStatusPresentation("unavailable"), {
      labelKey: "status.unavailable",
      pulse: false,
      tone: "amber"
    });
  });
});
