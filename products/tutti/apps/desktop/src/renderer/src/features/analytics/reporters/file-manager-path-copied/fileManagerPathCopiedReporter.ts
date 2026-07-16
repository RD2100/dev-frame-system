import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { FileManagerPathCopiedParams } from "./types.ts";

export class FileManagerPathCopiedReporter extends BaseAnalyticsReporter<FileManagerPathCopiedParams> {
  protected readonly eventName = "file_manager.path_copied";

  constructor(
    params: FileManagerPathCopiedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
