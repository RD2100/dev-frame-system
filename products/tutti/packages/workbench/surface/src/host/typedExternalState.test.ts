import assert from "node:assert/strict";
import test from "node:test";
import type { WorkbenchHostNodeDefinition } from "./types.ts";

interface TerminalNodeState {
  activePaneId: string;
  cwd: string;
}

interface TerminalWorkspaceState {
  workspaceName: string;
}

test("node definitions can type external node and workspace state", () => {
  const definition: WorkbenchHostNodeDefinition<
    TerminalNodeState,
    TerminalWorkspaceState
  > = {
    frame: { x: 100, y: 80, width: 640, height: 480 },
    renderBody(context) {
      const paneId: string = context.externalNodeState.activePaneId;
      const cwd: string = context.externalNodeState.cwd;
      const workspaceName: string =
        context.externalWorkspaceState.workspaceName;
      return `${paneId}:${cwd}:${workspaceName}`;
    },
    renderHeader(context) {
      const paneId: string = context.externalNodeState.activePaneId;
      const workspaceName: string =
        context.externalWorkspaceState.workspaceName;
      return `${workspaceName}:${paneId}`;
    },
    title: "Terminal",
    typeId: "terminal"
  };

  assert.equal(definition.typeId, "terminal");
});
