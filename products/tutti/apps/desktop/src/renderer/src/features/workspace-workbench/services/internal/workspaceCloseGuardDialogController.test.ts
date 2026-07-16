import assert from "node:assert/strict";
import test from "node:test";
import type { WorkbenchHostCloseDialogRequest } from "@tutti-os/workbench-surface";
import type { ReporterEventInput } from "../../../analytics/services/reporterService.interface.ts";
import { createWorkspaceCloseGuardDialogController } from "./workspaceCloseGuardDialogController.ts";

test("workspace close guard dialog controller confirms the active request", async () => {
  const controller = createWorkspaceCloseGuardDialogController();
  const request = createDialogRequest("Close window?");
  const confirmation = controller.requestConfirmation(request);

  assert.equal(controller.getSnapshot().request, request);

  controller.confirm();

  assert.equal(await confirmation, true);
  assert.deepEqual(controller.getSnapshot(), {
    request: null
  });
});

test("workspace close guard dialog controller cancels the active request", async () => {
  const controller = createWorkspaceCloseGuardDialogController();
  const request = createDialogRequest("Close node?");
  const confirmation = controller.requestConfirmation(request);

  controller.cancel();

  assert.equal(await confirmation, false);
  assert.deepEqual(controller.getSnapshot(), {
    request: null
  });
});

test("workspace close guard dialog controller tracks shown requests", () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const controller = createWorkspaceCloseGuardDialogController({
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => 1749124800000
  });

  void controller.requestConfirmation(createDialogRequest("Close window?"));

  assert.deepEqual(reporterCalls, [
    [
      {
        clientTS: 1749124800000,
        name: "workspace.close_guard_shown",
        params: {}
      }
    ]
  ]);
});

test("workspace close guard dialog controller tracks confirmed requests", async () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const controller = createWorkspaceCloseGuardDialogController({
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => 1749124800000
  });
  const confirmation = controller.requestConfirmation(
    createDialogRequest("Close window?")
  );

  controller.confirm();

  assert.equal(await confirmation, true);
  assert.deepEqual(reporterCalls[1], [
    {
      clientTS: 1749124800000,
      name: "workspace.close_guard_confirmed",
      params: {}
    }
  ]);
});

test("workspace close guard dialog controller tracks cancelled requests", async () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const controller = createWorkspaceCloseGuardDialogController({
    reporterService: createReporterService(reporterCalls),
    reporterNow: () => 1749124800000
  });
  const confirmation = controller.requestConfirmation(
    createDialogRequest("Close window?")
  );

  controller.cancel();

  assert.equal(await confirmation, false);
  assert.deepEqual(reporterCalls[1], [
    {
      clientTS: 1749124800000,
      name: "workspace.close_guard_cancelled",
      params: {}
    }
  ]);
});

test("workspace close guard dialog controller cancels stale requests", async () => {
  const controller = createWorkspaceCloseGuardDialogController();
  const firstRequest = createDialogRequest("First request");
  const secondRequest = createDialogRequest("Second request");
  const firstConfirmation = controller.requestConfirmation(firstRequest);

  const secondConfirmation = controller.requestConfirmation(secondRequest);

  assert.equal(await firstConfirmation, false);
  assert.equal(controller.getSnapshot().request, secondRequest);

  controller.confirm();

  assert.equal(await secondConfirmation, true);
});

test("workspace close guard dialog controller disposes pending requests", async () => {
  const controller = createWorkspaceCloseGuardDialogController();
  const confirmation = controller.requestConfirmation(
    createDialogRequest("Dispose request")
  );

  controller.dispose();

  assert.equal(await confirmation, false);
  assert.deepEqual(controller.getSnapshot(), {
    request: null
  });
});

test("workspace close guard dialog controller notifies snapshot changes", () => {
  const controller = createWorkspaceCloseGuardDialogController();
  const requests: (string | null)[] = [];
  controller.subscribe(() => {
    requests.push(controller.getSnapshot().request?.title ?? null);
  });

  void controller.requestConfirmation(createDialogRequest("Notify request"));
  controller.cancel();

  assert.deepEqual(requests, ["Notify request", null]);
});

function createDialogRequest(title: string): WorkbenchHostCloseDialogRequest {
  return {
    cancelLabel: "Cancel",
    confirmLabel: "Close",
    description: "There is work running.",
    scope: "window",
    title
  };
}

function createReporterService(calls: ReporterEventInput[][] = []) {
  return {
    async trackEvents(events: ReporterEventInput[]) {
      calls.push(events);
    }
  };
}
