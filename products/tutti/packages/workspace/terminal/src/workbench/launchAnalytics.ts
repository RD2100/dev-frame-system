import type { WorkbenchHostLaunchRequest } from "@tutti-os/workbench-surface";

export type TerminalLaunchAnalyticsTrigger =
  | "agent_command"
  | "dock"
  | "keyboard"
  | "launchpad";

export function resolveTerminalLaunchAnalyticsTrigger(
  request: WorkbenchHostLaunchRequest
): TerminalLaunchAnalyticsTrigger {
  switch (request.reason) {
    case "dock":
      return "dock";
    case "launchpad":
      return "launchpad";
    case "shortcut":
      return "keyboard";
    case "host":
      return hasInitialInput(request.payload) ? "agent_command" : "launchpad";
    default:
      return "launchpad";
  }
}

function hasInitialInput(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const typed = payload as { initialInput?: unknown };
  return (
    typeof typed.initialInput === "string" &&
    typed.initialInput.trim().length > 0
  );
}
