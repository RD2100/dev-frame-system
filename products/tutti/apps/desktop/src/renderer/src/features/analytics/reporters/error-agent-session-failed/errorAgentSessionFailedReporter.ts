import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { ErrorAgentSessionFailedParams } from "./types.ts";

export class ErrorAgentSessionFailedReporter extends BaseAnalyticsReporter<ErrorAgentSessionFailedParams> {
  protected readonly eventName = "error.agent_session_failed";

  constructor(
    params: ErrorAgentSessionFailedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
