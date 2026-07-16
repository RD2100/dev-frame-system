import type {
  IssueManagerOpenSource,
  IssueManagerOpenTrigger
} from "@tutti-os/workspace-issue-manager/contracts";
import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface IssueManagerOpenedParams extends AnalyticsReporterParams {
  source: IssueManagerOpenSource;
  trigger: IssueManagerOpenTrigger;
}
