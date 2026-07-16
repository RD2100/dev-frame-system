import { resolveTerminalScrollbackDelta } from "../core/index.ts";

export interface TerminalSurfaceOutputPlanInput {
  committedRawOutput: string;
  contentEpoch: number;
  nextContentEpoch: number;
  rawOutput: string;
}

export interface TerminalSurfaceOutputPlan {
  nextCommittedRawOutput: string;
  nextContentEpoch: number;
  reset: boolean;
  write: string | null;
}

export function resolveTerminalSurfaceOutputPlan(
  input: TerminalSurfaceOutputPlanInput
): TerminalSurfaceOutputPlan | null {
  if (
    input.nextContentEpoch === 0 &&
    input.rawOutput.length === 0 &&
    input.committedRawOutput.length > 0
  ) {
    return null;
  }

  if (input.nextContentEpoch !== input.contentEpoch) {
    if (input.rawOutput === input.committedRawOutput) {
      return {
        nextCommittedRawOutput: input.committedRawOutput,
        nextContentEpoch: input.nextContentEpoch,
        reset: false,
        write: null
      };
    }

    return {
      nextCommittedRawOutput: input.rawOutput,
      nextContentEpoch: input.nextContentEpoch,
      reset: true,
      write: input.rawOutput || null
    };
  }

  if (input.rawOutput === input.committedRawOutput) {
    return null;
  }

  const delta = resolveTerminalScrollbackDelta(
    input.committedRawOutput,
    input.rawOutput
  );

  return {
    nextCommittedRawOutput: input.rawOutput,
    nextContentEpoch: input.nextContentEpoch,
    reset: !delta,
    write: delta || input.rawOutput || null
  };
}
