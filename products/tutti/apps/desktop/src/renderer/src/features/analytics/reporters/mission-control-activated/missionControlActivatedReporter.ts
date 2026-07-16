import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { MissionControlActivatedParams } from "./types.ts";

export class MissionControlActivatedReporter extends BaseAnalyticsReporter<MissionControlActivatedParams> {
  protected readonly eventName = "mission_control.activated";

  constructor(
    params: MissionControlActivatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
