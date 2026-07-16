import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { BrowserClosedParams } from "./types.ts";

export class BrowserClosedReporter extends BaseAnalyticsReporter<BrowserClosedParams> {
  protected readonly eventName = "browser.closed";

  constructor(
    params: BrowserClosedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
