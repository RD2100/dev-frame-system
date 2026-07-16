import type { JSX } from "react";
import { AgentTerminalBlock } from "./terminal/AgentTerminalBlock";
import {
  stringValue,
  type AgentToolRendererProps
} from "./agentToolContentShared";
import { getCommandRenderData } from "./render-data/agentToolRenderData";

export function AgentBashContent({
  call
}: AgentToolRendererProps): JSX.Element {
  "use memo";
  const commandData = getCommandRenderData(call);
  const fallbackErrorText =
    commandData.status === "failed" &&
    !commandData.stdout &&
    !commandData.stderr
      ? stringValue(call.error?.message)
      : null;

  return (
    <div className="workspace-agents-status-panel__detail-tool-body workspace-agents-status-panel__detail-tool-body--plain">
      <AgentTerminalBlock
        command={commandData.command}
        stdout={commandData.stdout}
        stderr={commandData.stderr || fallbackErrorText || ""}
        exitCode={commandData.exitCode}
        durationMs={commandData.durationMs}
        status={commandData.status}
      />
    </div>
  );
}
