import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { FilePreviewOpenedParams } from "./types.ts";

export class FilePreviewOpenedReporter extends BaseAnalyticsReporter<FilePreviewOpenedParams> {
  protected readonly eventName = "file_preview.opened";

  constructor(
    params: FilePreviewOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
