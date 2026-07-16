import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { FileManagerFileCreatedParams } from "./types.ts";

export class FileManagerFileCreatedReporter extends BaseAnalyticsReporter<FileManagerFileCreatedParams> {
  protected readonly eventName = "file_manager.file_created";

  constructor(
    params: FileManagerFileCreatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
