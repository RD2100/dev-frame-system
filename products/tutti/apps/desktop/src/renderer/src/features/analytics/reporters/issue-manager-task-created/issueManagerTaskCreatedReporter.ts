import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerTaskCreatedParams } from "./types.ts";

export class IssueManagerTaskCreatedReporter extends BaseAnalyticsReporter<IssueManagerTaskCreatedParams> {
  protected readonly eventName = "issue_manager.task_created";

  constructor(
    params: IssueManagerTaskCreatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
