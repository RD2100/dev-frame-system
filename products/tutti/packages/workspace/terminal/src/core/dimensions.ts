export interface TerminalScreenDimensionsLike {
  cols?: number | null;
  rows?: number | null;
}

export interface TerminalScreenDimensions {
  cols: number;
  rows: number;
}

export function resolveInitialTerminalDimensions(
  state: TerminalScreenDimensionsLike | null | undefined
): TerminalScreenDimensions | null {
  if (!state) {
    return null;
  }

  const cols = normalizeTerminalDimension(state.cols);
  const rows = normalizeTerminalDimension(state.rows);

  if (cols === null || rows === null) {
    return null;
  }

  return { cols, rows };
}

function normalizeTerminalDimension(
  value: number | null | undefined
): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }

  const normalized = Math.floor(value);
  return normalized > 0 ? normalized : null;
}
