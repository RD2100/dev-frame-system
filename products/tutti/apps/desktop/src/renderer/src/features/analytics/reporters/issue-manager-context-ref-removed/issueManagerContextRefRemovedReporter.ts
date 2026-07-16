import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { IssueManagerContextRefRemovedParams } from "./types.ts";

export class IssueManagerContextRefRemovedReporter extends BaseAnalyticsReporter<IssueManagerContextRefRemovedParams> {
  protected readonly eventName = "issue_manager.context_ref_removed";

  constructor(
    params: IssueManagerContextRefRemovedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
