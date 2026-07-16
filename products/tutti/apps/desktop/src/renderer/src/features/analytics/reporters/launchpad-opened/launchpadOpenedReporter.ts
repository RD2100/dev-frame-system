import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { LaunchpadOpenedParams } from "./types.ts";

export class LaunchpadOpenedReporter extends BaseAnalyticsReporter<LaunchpadOpenedParams> {
  protected readonly eventName = "launchpad.opened";

  constructor(
    params: LaunchpadOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
