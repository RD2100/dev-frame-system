import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentWorkspaceFileReferencedParams } from "./types.ts";

export class AgentWorkspaceFileReferencedReporter extends BaseAnalyticsReporter<AgentWorkspaceFileReferencedParams> {
  protected readonly eventName = "agent.workspace_file_referenced";

  constructor(
    params: AgentWorkspaceFileReferencedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
