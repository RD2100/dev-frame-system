import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { DaemonDisconnectedParams } from "./types.ts";

export class DaemonDisconnectedReporter extends BaseAnalyticsReporter<DaemonDisconnectedParams> {
  protected readonly eventName = "daemon.disconnected";

  constructor(
    params: DaemonDisconnectedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
