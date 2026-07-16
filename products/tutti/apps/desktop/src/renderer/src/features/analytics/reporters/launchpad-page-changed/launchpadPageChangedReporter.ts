import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { LaunchpadPageChangedParams } from "./types.ts";

export class LaunchpadPageChangedReporter extends BaseAnalyticsReporter<LaunchpadPageChangedParams> {
  protected readonly eventName = "launchpad.page_changed";

  constructor(
    params: LaunchpadPageChangedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
