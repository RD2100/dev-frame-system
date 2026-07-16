import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerTaskRunInitiatedParams } from "./types.ts";

export class IssueManagerTaskRunInitiatedReporter extends BaseAnalyticsReporter<IssueManagerTaskRunInitiatedParams> {
  protected readonly eventName = "issue_manager.task_run_initiated";

  constructor(
    params: IssueManagerTaskRunInitiatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
