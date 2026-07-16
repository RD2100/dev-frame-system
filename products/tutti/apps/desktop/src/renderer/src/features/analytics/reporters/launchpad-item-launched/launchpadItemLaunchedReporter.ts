import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { LaunchpadItemLaunchedParams } from "./types.ts";

export class LaunchpadItemLaunchedReporter extends BaseAnalyticsReporter<LaunchpadItemLaunchedParams> {
  protected readonly eventName = "launchpad.item_launched";

  constructor(
    params: LaunchpadItemLaunchedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
