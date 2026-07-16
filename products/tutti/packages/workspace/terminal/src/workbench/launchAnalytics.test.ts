import assert from "node:assert/strict";
import test from "node:test";
import type { WorkbenchHostLaunchRequest } from "@tutti-os/workbench-surface";
import { resolveTerminalLaunchAnalyticsTrigger } from "./launchAnalytics.ts";

const requestContext = {
  layoutConstraints: {
    minHeight: 180,
    minWidth: 280,
    safeArea: {
      bottom: 0,
      left: 0,
      right: 0,
      top: 0
    },
    surfacePadding: 24
  },
  surfaceSize: {
    height: 720,
    width: 1280
  }
} satisfies Pick<
  WorkbenchHostLaunchRequest,
  "layoutConstraints" | "surfaceSize"
>;

test("terminal launch analytics trigger resolves from launch source", () => {
  const cases: Array<{
    expectedTrigger: string;
    request: WorkbenchHostLaunchRequest;
  }> = [
    {
      expectedTrigger: "dock",
      request: {
        dockEntryId: "workspace-terminal",
        ...requestContext,
        reason: "dock",
        typeId: "workspace-terminal",
        workspaceId: "workspace-1"
      }
    },
    {
      expectedTrigger: "keyboard",
      request: {
        dockEntryId: "workspace-terminal",
        ...requestContext,
        reason: "shortcut",
        typeId: "workspace-terminal",
        workspaceId: "workspace-1"
      }
    },
    {
      expectedTrigger: "launchpad",
      request: {
        dockEntryId: "workspace-terminal",
        ...requestContext,
        payload: {},
        reason: "launchpad",
        typeId: "workspace-terminal",
        workspaceId: "workspace-1"
      }
    },
    {
      expectedTrigger: "agent_command",
      request: {
        ...requestContext,
        payload: {
          initialInput: "pnpm test\n"
        },
        reason: "host",
        typeId: "workspace-terminal",
        workspaceId: "workspace-1"
      }
    }
  ];

  for (const { expectedTrigger, request } of cases) {
    assert.equal(
      resolveTerminalLaunchAnalyticsTrigger(request),
      expectedTrigger
    );
  }
});
