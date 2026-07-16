import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { TerminalClosedParams } from "./types.ts";

export class TerminalClosedReporter extends BaseAnalyticsReporter<TerminalClosedParams> {
  protected readonly eventName = "terminal.closed";

  constructor(
    params: TerminalClosedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
