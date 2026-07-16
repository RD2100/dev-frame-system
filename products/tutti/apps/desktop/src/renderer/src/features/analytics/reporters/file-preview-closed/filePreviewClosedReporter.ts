import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { FilePreviewClosedParams } from "./types.ts";

export class FilePreviewClosedReporter extends BaseAnalyticsReporter<FilePreviewClosedParams> {
  protected readonly eventName = "file_preview.closed";

  constructor(
    params: FilePreviewClosedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
