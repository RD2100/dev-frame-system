import { AgentSettingsModelChangedReporter } from "../../../analytics/reporters/agent-settings-model-changed/agentSettingsModelChangedReporter.ts";
import { AgentSettingsPermissionModeChangedReporter } from "../../../analytics/reporters/agent-settings-permission-mode-changed/agentSettingsPermissionModeChangedReporter.ts";
import { AgentSettingsReasoningEffortChangedReporter } from "../../../analytics/reporters/agent-settings-reasoning-effort-changed/agentSettingsReasoningEffortChangedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";
import { createOptionalReporterService } from "./agentMessageSentAnalytics.ts";
import { isCustomAgentSessionModel } from "./agentSessionStartedAnalytics.ts";
import {
  resolveComposerPermissionMode,
  type AgentHostAgentSessionComposerSettings
} from "./desktopAgentHostProjection.ts";

export async function reportAgentSessionSettingsChanges(input: {
  agentSessionId: string | null;
  nextSettings: AgentHostAgentSessionComposerSettings;
  previousSettings: AgentHostAgentSessionComposerSettings | undefined;
  provider: string;
  reporterNow?: () => number;
  reporterService?: Pick<IReporterService, "trackEvents">;
}): Promise<void> {
  const reporterDependencies = {
    reporterService: createOptionalReporterService(input.reporterService),
    now: input.reporterNow
  };
  const previousModel = input.previousSettings?.model ?? null;
  const nextModel = input.nextSettings.model ?? null;
  if (nextModel !== previousModel) {
    await new AgentSettingsModelChangedReporter(
      {
        agentSessionId: input.agentSessionId,
        isCustomModel: isCustomAgentSessionModel(nextModel),
        provider: input.provider
      },
      reporterDependencies
    ).report();
  }

  const previousPermissionMode = resolveComposerPermissionMode(
    input.previousSettings
  );
  const nextPermissionMode = resolveComposerPermissionMode(input.nextSettings);
  if (nextPermissionMode && nextPermissionMode !== previousPermissionMode) {
    await new AgentSettingsPermissionModeChangedReporter(
      {
        agentSessionId: input.agentSessionId,
        fromMode: previousPermissionMode,
        provider: input.provider,
        toMode: nextPermissionMode
      },
      reporterDependencies
    ).report();
  }

  const previousReasoningEffort = normalizedOptionalSetting(
    input.previousSettings?.reasoningEffort
  );
  const nextReasoningEffort = normalizedOptionalSetting(
    input.nextSettings.reasoningEffort
  );
  if (nextReasoningEffort && nextReasoningEffort !== previousReasoningEffort) {
    await new AgentSettingsReasoningEffortChangedReporter(
      {
        agentSessionId: input.agentSessionId,
        fromEffort: previousReasoningEffort,
        provider: input.provider,
        toEffort: nextReasoningEffort
      },
      reporterDependencies
    ).report();
  }
}

function normalizedOptionalSetting(
  value: string | null | undefined
): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}
