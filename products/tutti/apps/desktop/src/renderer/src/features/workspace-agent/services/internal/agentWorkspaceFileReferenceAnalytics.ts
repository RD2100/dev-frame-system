import type { WorkspaceFileReference } from "@tutti-os/workspace-file-reference/contracts";
import { AgentWorkspaceFileReferencedReporter } from "../../../analytics/reporters/agent-workspace-file-referenced/agentWorkspaceFileReferencedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";
import { createOptionalReporterService } from "./agentMessageSentAnalytics.ts";
import { resolveDesktopAgentGUIProvider } from "./desktopAgentHostProjection.ts";

export interface AgentWorkspaceFileReferenceTracker {
  track(input: {
    provider?: string | null;
    references: readonly WorkspaceFileReference[];
  }): Promise<void>;
}

export function createAgentWorkspaceFileReferenceTracker(input: {
  reporterNow?: () => number;
  reporterService?: Pick<IReporterService, "trackEvents">;
}): AgentWorkspaceFileReferenceTracker {
  return {
    async track(selection) {
      if (selection.references.length === 0) {
        return;
      }
      await new AgentWorkspaceFileReferencedReporter(
        {
          hasDirectory: selection.references.some(
            (reference) => reference.kind === "folder"
          ),
          provider: resolveDesktopAgentGUIProvider(selection.provider),
          referenceCount: selection.references.length
        },
        {
          reporterService: createOptionalReporterService(input.reporterService),
          now: input.reporterNow
        }
      ).report();
    }
  };
}
