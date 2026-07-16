import type {
  TerminalNodeExternalState,
  TerminalSessionStatus
} from "../contracts/index.ts";

export const terminalSessionLostMessage = "Terminal session was lost.";

export interface TerminalSessionStatusProjection {
  lastError: string | null;
  status: TerminalSessionStatus;
}

export function createTerminalSessionExitProjection(): TerminalSessionStatusProjection {
  return {
    lastError: null,
    status: "exited"
  };
}

export function createTerminalSessionFailedProjection(
  lastError = terminalSessionLostMessage
): TerminalSessionStatusProjection {
  return {
    lastError,
    status: "failed"
  };
}

export function applyTerminalSessionStatusProjection<
  THostMetadata extends Record<string, unknown> = Record<string, unknown>
>(
  current: TerminalNodeExternalState<THostMetadata>,
  projection: TerminalSessionStatusProjection,
  now: () => string = () => new Date().toISOString()
): TerminalNodeExternalState<THostMetadata> {
  if (
    current.endedAt &&
    isTerminalSessionEndedStatus(current.status) &&
    !isTerminalSessionEndedStatus(projection.status)
  ) {
    return current;
  }

  return {
    ...current,
    endedAt: isTerminalSessionEndedStatus(projection.status)
      ? (current.endedAt ?? now())
      : current.endedAt,
    lastError: projection.lastError,
    status: projection.status
  };
}

export function applyTerminalSessionTitleProjection<
  THostMetadata extends Record<string, unknown> = Record<string, unknown>
>(
  current: TerminalNodeExternalState<THostMetadata>,
  title: string
): TerminalNodeExternalState<THostMetadata> {
  return {
    ...current,
    title
  };
}

export function isTerminalSessionEndedStatus(
  status: TerminalSessionStatus
): boolean {
  return status === "exited" || status === "failed";
}
