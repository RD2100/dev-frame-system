import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerTaskDeletedParams } from "./types.ts";

export class IssueManagerTaskDeletedReporter extends BaseAnalyticsReporter<IssueManagerTaskDeletedParams> {
  protected readonly eventName = "issue_manager.task_deleted";

  constructor(
    params: IssueManagerTaskDeletedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
