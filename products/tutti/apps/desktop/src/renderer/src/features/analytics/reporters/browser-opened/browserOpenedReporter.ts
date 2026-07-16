import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { BrowserOpenedParams } from "./types.ts";

export class BrowserOpenedReporter extends BaseAnalyticsReporter<BrowserOpenedParams> {
  protected readonly eventName = "browser.opened";

  constructor(
    params: BrowserOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
