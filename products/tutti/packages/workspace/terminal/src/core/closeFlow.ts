import type {
  TerminalCloseGuardResult,
  TerminalLaunchService,
  TerminalSessionStatus
} from "../contracts/index.ts";
import { createTerminalCloseDiagnostics } from "./sessionDiagnostics.ts";
import type { TerminalNodeFeature } from "./feature.ts";
import { isTerminalSessionEndedStatus } from "./sessionProjection.ts";

export type TerminalCloseConfirmation = (
  guard: TerminalCloseGuardResult
) => Promise<boolean> | boolean;

export type TerminalCloseResult = "closed" | "kept-open";

export interface CloseTerminalSessionInput {
  confirm?: TerminalCloseConfirmation;
  feature: Pick<TerminalNodeFeature, "closeGuard" | "diagnostics"> & {
    launchService: Pick<TerminalLaunchService, "terminate">;
  };
  sessionId: string | null | undefined;
  status?: TerminalSessionStatus | null | undefined;
}

export async function closeTerminalSession({
  confirm,
  feature,
  sessionId,
  status
}: CloseTerminalSessionInput): Promise<TerminalCloseResult> {
  if (!sessionId || (status && isTerminalSessionEndedStatus(status))) {
    return "closed";
  }

  const closeDiagnostics = createTerminalCloseDiagnostics({
    diagnostics: feature.diagnostics,
    sessionId
  });

  closeDiagnostics.requested();
  const guard = await feature.closeGuard.check({ sessionId });
  if (isTerminalSessionEndedStatus(guard.status)) {
    closeDiagnostics.confirmed();
    return "closed";
  }
  if (guard.requiresConfirmation) {
    const confirmed = await confirm?.(guard);
    if (!confirmed) {
      return "kept-open";
    }
  }

  await feature.launchService.terminate({ sessionId });
  closeDiagnostics.confirmed();
  return "closed";
}
