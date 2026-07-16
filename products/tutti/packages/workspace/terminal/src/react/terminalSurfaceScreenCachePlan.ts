export type TerminalSurfaceScreenCachePlan =
  | { action: "remove" }
  | {
      action: "save";
      rawSnapshot: string;
      serialized: string;
    }
  | { action: "skip" };

export function resolveTerminalSurfaceScreenCachePlan(input: {
  hasPendingWrites: boolean;
  rawSnapshot: string;
  serialized: string;
}): TerminalSurfaceScreenCachePlan {
  if (input.hasPendingWrites) {
    return {
      action: input.serialized ? "skip" : "remove"
    };
  }

  if (!input.serialized) {
    return { action: "skip" };
  }

  return {
    action: "save",
    rawSnapshot: input.rawSnapshot,
    serialized: input.serialized
  };
}
