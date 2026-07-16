import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerTopicChangedParams } from "./types.ts";

export class IssueManagerTopicChangedReporter extends BaseAnalyticsReporter<IssueManagerTopicChangedParams> {
  protected readonly eventName = "issue_manager.topic_changed";

  constructor(
    params: IssueManagerTopicChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
