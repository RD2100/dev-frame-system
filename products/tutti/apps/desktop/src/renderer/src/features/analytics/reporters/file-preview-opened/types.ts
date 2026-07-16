import type { AnalyticsReporterParams } from "../baseReporter.ts";
import type {
  AnalyticsOpenSource,
  AnalyticsOpenTrigger
} from "../openedSource.ts";

export interface FilePreviewOpenedParams extends AnalyticsReporterParams {
  fileExtension: string | null;
  source: AnalyticsOpenSource;
  trigger: AnalyticsOpenTrigger;
}
