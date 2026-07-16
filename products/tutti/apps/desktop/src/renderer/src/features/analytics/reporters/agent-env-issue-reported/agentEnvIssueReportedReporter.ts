import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AgentEnvIssueReportedParams } from "./types.ts";

export class AgentEnvIssueReportedReporter extends BaseAnalyticsReporter<AgentEnvIssueReportedParams> {
  protected readonly eventName = "agent.env_issue_reported";

  constructor(
    params: AgentEnvIssueReportedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
