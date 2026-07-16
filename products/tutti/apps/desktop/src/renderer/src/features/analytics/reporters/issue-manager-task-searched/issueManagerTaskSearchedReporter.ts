import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerTaskSearchedParams } from "./types.ts";

export class IssueManagerTaskSearchedReporter extends BaseAnalyticsReporter<IssueManagerTaskSearchedParams> {
  protected readonly eventName = "issue_manager.task_searched";

  constructor(
    params: IssueManagerTaskSearchedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
