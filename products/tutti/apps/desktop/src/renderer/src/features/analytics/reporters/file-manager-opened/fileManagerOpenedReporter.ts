import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { FileManagerOpenedParams } from "./types.ts";

export class FileManagerOpenedReporter extends BaseAnalyticsReporter<FileManagerOpenedParams> {
  protected readonly eventName = "file_manager.opened";

  constructor(
    params: FileManagerOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
