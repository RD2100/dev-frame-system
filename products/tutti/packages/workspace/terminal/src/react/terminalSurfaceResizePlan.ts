export interface TerminalSurfaceSize {
  cols: number;
  rows: number;
}

export function resolveTerminalSurfaceResizePlan(input: {
  lastSize: TerminalSurfaceSize | null;
  nextSize: TerminalSurfaceSize;
}): TerminalSurfaceSize | null {
  if (
    input.lastSize?.cols === input.nextSize.cols &&
    input.lastSize.rows === input.nextSize.rows
  ) {
    return null;
  }
  return input.nextSize;
}
