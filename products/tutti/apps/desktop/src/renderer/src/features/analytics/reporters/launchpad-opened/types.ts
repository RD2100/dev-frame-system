import type { AnalyticsReporterParams } from "../baseReporter.ts";
import type {
  AnalyticsOpenSource,
  AnalyticsOpenTrigger
} from "../openedSource.ts";

export interface LaunchpadOpenedParams extends AnalyticsReporterParams {
  source: AnalyticsOpenSource;
  totalItems: number;
  trigger: AnalyticsOpenTrigger;
}
