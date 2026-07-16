import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { MissionControlDeactivatedParams } from "./types.ts";

export class MissionControlDeactivatedReporter extends BaseAnalyticsReporter<MissionControlDeactivatedParams> {
  protected readonly eventName = "mission_control.deactivated";

  constructor(
    params: MissionControlDeactivatedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
