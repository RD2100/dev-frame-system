import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { DaemonStartupFailedParams } from "./types.ts";

export class DaemonStartupFailedReporter extends BaseAnalyticsReporter<DaemonStartupFailedParams> {
  protected readonly eventName = "daemon.startup_failed";

  constructor(
    params: DaemonStartupFailedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
