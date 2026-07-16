import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerIssueSavedParams } from "./types.ts";

export class IssueManagerIssueSavedReporter extends BaseAnalyticsReporter<IssueManagerIssueSavedParams> {
  protected readonly eventName = "issue_manager.issue_saved";

  constructor(
    params: IssueManagerIssueSavedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
