import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { LaunchpadClosedParams } from "./types.ts";

export class LaunchpadClosedReporter extends BaseAnalyticsReporter<LaunchpadClosedParams> {
  protected readonly eventName = "launchpad.closed";

  constructor(
    params: LaunchpadClosedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
