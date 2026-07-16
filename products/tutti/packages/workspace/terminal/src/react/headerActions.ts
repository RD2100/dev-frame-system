import type { ReactNode } from "react";

export function hasTerminalHeaderDefaultActions(
  defaultActions: ReactNode
): boolean {
  return defaultActions !== undefined && defaultActions !== null;
}
