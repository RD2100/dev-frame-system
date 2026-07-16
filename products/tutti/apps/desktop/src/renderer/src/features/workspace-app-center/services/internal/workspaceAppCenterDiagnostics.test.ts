import assert from "node:assert/strict";
import test from "node:test";
import type { DesktopRuntimeApi } from "@preload/types";
import type { DesktopRendererDiagnosticPayload } from "@shared/contracts/ipc";
import { recordWorkspaceAppCenterOperationFailure } from "./workspaceAppCenterDiagnostics.ts";

test("recordWorkspaceAppCenterOperationFailure records renderer diagnostic payload", () => {
  const diagnostics: DesktopRendererDiagnosticPayload[] = [];
  const runtimeApi: Pick<DesktopRuntimeApi, "logRendererDiagnostic"> = {
    async logRendererDiagnostic(payload) {
      diagnostics.push(payload);
    }
  };

  recordWorkspaceAppCenterOperationFailure({
    details: {
      appId: "app-1",
      operation: "workspace_app.install",
      uiAction: "install_app",
      workspaceId: "workspace-1"
    },
    error: {
      error: {
        code: "workspace_app_not_found",
        developerMessage: "workspace app app-1 was not found",
        params: { appId: "app-1" },
        reason: "missing_app",
        retryable: true
      }
    },
    runtimeApi,
    toastMessage: "Could not install app"
  });

  assert.deepEqual(diagnostics, [
    {
      details: {
        appId: "app-1",
        developerMessage: "workspace app app-1 was not found",
        errorCode: "workspace_app_not_found",
        operation: "workspace_app.install",
        params: { appId: "app-1" },
        reason: "missing_app",
        retryable: true,
        statusCode: 0,
        toastMessage: "Could not install app",
        uiAction: "install_app",
        workspaceId: "workspace-1"
      },
      event: "workspace_app_center_operation_failed",
      level: "warn",
      source: "workspace-app-center",
      workspaceId: "workspace-1"
    }
  ]);
});
