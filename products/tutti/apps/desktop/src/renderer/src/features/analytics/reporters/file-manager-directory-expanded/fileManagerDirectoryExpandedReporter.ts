import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { FileManagerDirectoryExpandedParams } from "./types.ts";

export class FileManagerDirectoryExpandedReporter extends BaseAnalyticsReporter<FileManagerDirectoryExpandedParams> {
  protected readonly eventName = "file_manager.directory_expanded";

  constructor(
    params: FileManagerDirectoryExpandedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
