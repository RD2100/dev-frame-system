import { getTuttidProtocolErrorCode } from "@tutti-os/client-tuttid-ts";
import {
  closeTerminalSession,
  type TerminalNodeFeature
} from "@tutti-os/workspace-terminal";
import type { TerminalNodeExternalState } from "@tutti-os/workspace-terminal/contracts";
import type { WorkbenchHostHandle } from "@tutti-os/workbench-surface";

export function shouldCloseTerminalNodeAfterError(error: unknown): boolean {
  switch (getTuttidProtocolErrorCode(error)) {
    case "workspace_terminal_not_found":
    case "workspace_terminal_not_running":
      return true;
    default:
      return false;
  }
}

export function shouldCloseTerminalNodeAfterCloseFailure(input: {
  error: unknown;
  status?: string | null;
}): boolean {
  if (shouldCloseTerminalNodeAfterError(input.error)) {
    return true;
  }

  if (!input.status) {
    return false;
  }

  return isEndedTerminalStatus(input.status);
}

export async function closeWindowTerminalNodes(input: {
  getTerminalState(sessionId: string): TerminalNodeExternalState | null;
  host: WorkbenchHostHandle;
  logFailure?: (input: { error: unknown; sessionId: string }) => void;
  terminalFeature: Pick<TerminalNodeFeature, "closeGuard" | "diagnostics"> & {
    launchService: Pick<TerminalNodeFeature["launchService"], "terminate">;
  };
  terminalTypeId?: string;
}): Promise<boolean> {
  const terminalNodes = input.host
    .getSnapshot()
    .nodes.filter(
      (node) =>
        node.data.typeId === (input.terminalTypeId ?? "workspace-terminal")
    );

  for (const node of terminalNodes) {
    const sessionId = node.data.instanceKey ?? node.data.instanceId;
    const terminalState = input.getTerminalState(sessionId);

    try {
      const result = await closeTerminalSession({
        confirm: () => true,
        feature: input.terminalFeature,
        sessionId,
        status: terminalState?.status
      });
      if (result !== "closed") {
        return false;
      }
      input.host.closeNode(node.id);
    } catch (error) {
      input.logFailure?.({ error, sessionId });
      if (
        !shouldCloseTerminalNodeAfterCloseFailure({
          error,
          status: terminalState?.status
        })
      ) {
        return false;
      }
      input.host.closeNode(node.id);
    }
  }

  return true;
}

function isEndedTerminalStatus(status: string): boolean {
  return status === "exited" || status === "failed";
}
