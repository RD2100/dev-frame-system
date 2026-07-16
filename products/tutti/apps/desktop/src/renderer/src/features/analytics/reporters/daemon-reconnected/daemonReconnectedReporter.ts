import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { DaemonReconnectedParams } from "./types.ts";

export class DaemonReconnectedReporter extends BaseAnalyticsReporter<DaemonReconnectedParams> {
  protected readonly eventName = "daemon.reconnected";

  constructor(
    params: DaemonReconnectedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
