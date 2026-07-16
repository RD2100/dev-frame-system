import assert from "node:assert/strict";
import test from "node:test";
import { toggleWorkspaceAgentMessageCenter } from "./workspaceAgentMessageCenterToggle.ts";

test("workspace agent message center toggle reports only when opening", () => {
  const states: boolean[] = [];
  let openedReports = 0;

  toggleWorkspaceAgentMessageCenter({
    onOpened() {
      openedReports += 1;
    },
    open: false,
    setOpen(nextOpen) {
      states.push(nextOpen);
    }
  });
  toggleWorkspaceAgentMessageCenter({
    onOpened() {
      openedReports += 1;
    },
    open: true,
    setOpen(nextOpen) {
      states.push(nextOpen);
    }
  });

  assert.deepEqual(states, [true, false]);
  assert.equal(openedReports, 1);
});
