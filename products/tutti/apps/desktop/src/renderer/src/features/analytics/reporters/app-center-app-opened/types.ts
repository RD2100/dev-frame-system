import type { AnalyticsReporterParams } from "../baseReporter.ts";

export interface AppCenterAppOpenedParams extends AnalyticsReporterParams {
  readonly appId: string;
  readonly appSource: "builtin" | "generated" | "imported" | "local-dev";
  readonly prevStatus:
    | "failed"
    | "idle"
    | "installed_pending_restart"
    | "installing"
    | "preparing"
    | "running"
    | "starting"
    | "stopping"
    | "unavailable";
}
