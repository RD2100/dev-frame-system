import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerTaskSavedParams } from "./types.ts";

export class IssueManagerTaskSavedReporter extends BaseAnalyticsReporter<IssueManagerTaskSavedParams> {
  protected readonly eventName = "issue_manager.task_saved";

  constructor(
    params: IssueManagerTaskSavedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
