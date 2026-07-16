import type { AnalyticsReporterParams } from "../baseReporter.ts";
import type {
  AnalyticsOpenSource,
  AnalyticsOpenTrigger
} from "../openedSource.ts";

export interface FileManagerOpenedParams extends AnalyticsReporterParams {
  source: AnalyticsOpenSource;
  trigger: AnalyticsOpenTrigger;
}
