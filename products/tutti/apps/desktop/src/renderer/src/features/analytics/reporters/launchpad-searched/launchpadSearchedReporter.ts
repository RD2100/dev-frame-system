import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { LaunchpadSearchedParams } from "./types.ts";

export class LaunchpadSearchedReporter extends BaseAnalyticsReporter<LaunchpadSearchedParams> {
  protected readonly eventName = "launchpad.searched";

  constructor(
    params: LaunchpadSearchedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
