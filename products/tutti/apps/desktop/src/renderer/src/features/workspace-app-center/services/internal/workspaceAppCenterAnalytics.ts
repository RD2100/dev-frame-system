import { AppCenterOpenedReporter } from "../../../analytics/reporters/app-center-opened/appCenterOpenedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";

export function createWorkspaceAppCenterOpenedLease(input: {
  reporterService?: Pick<IReporterService, "trackEvents">;
}) {
  if (!input.reporterService) {
    return null;
  }

  void new AppCenterOpenedReporter(
    {},
    {
      reporterService: input.reporterService
    }
  ).report();

  return {
    release() {}
  };
}
