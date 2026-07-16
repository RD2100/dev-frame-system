import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerContextRefAddedParams } from "./types.ts";

export class IssueManagerContextRefAddedReporter extends BaseAnalyticsReporter<IssueManagerContextRefAddedParams> {
  protected readonly eventName = "issue_manager.context_ref_added";

  constructor(
    params: IssueManagerContextRefAddedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
