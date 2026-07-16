import type {
  TerminalCloseGuardService,
  TerminalNodeExternalState
} from "../contracts/index.ts";
import { isTerminalSessionEndedStatus } from "../core/sessionProjection.ts";

export interface ResolveTerminalWindowCloseEffectInput {
  closeGuard: TerminalCloseGuardService;
  description: string;
  externalNodeState: TerminalNodeExternalState | null;
  nodeId: string;
  sessionId?: string | null;
  title: string;
  typeId: string;
}

export async function resolveTerminalWindowCloseEffect({
  closeGuard,
  description,
  externalNodeState,
  nodeId,
  sessionId,
  title,
  typeId
}: ResolveTerminalWindowCloseEffectInput) {
  const status = externalNodeState?.status ?? "created";
  if (status === "created" || isTerminalSessionEndedStatus(status)) {
    return null;
  }

  const resolvedSessionId = sessionId ?? externalNodeState?.sessionId ?? null;
  if (resolvedSessionId) {
    try {
      const guard = await closeGuard.check({ sessionId: resolvedSessionId });
      if (
        !guard.requiresConfirmation ||
        guard.reason === "not-running" ||
        isTerminalSessionEndedStatus(guard.status)
      ) {
        return null;
      }
    } catch {
      // Fall back to a conservative close effect when guard lookup fails.
    }
  }

  return {
    description,
    nodeId,
    title: externalNodeState?.title?.trim() || title,
    typeId
  };
}
