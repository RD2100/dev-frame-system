import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { TerminalOpenedParams } from "./types.ts";

export class TerminalOpenedReporter extends BaseAnalyticsReporter<TerminalOpenedParams> {
  protected readonly eventName = "terminal.opened";

  constructor(
    params: TerminalOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
