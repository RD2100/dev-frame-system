import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerOpenedParams } from "./types.ts";

export class IssueManagerOpenedReporter extends BaseAnalyticsReporter<IssueManagerOpenedParams> {
  protected readonly eventName = "issue_manager.opened";

  constructor(
    params: IssueManagerOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
