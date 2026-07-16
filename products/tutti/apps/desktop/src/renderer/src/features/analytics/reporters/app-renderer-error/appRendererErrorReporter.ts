import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { AppRendererErrorParams } from "./types.ts";

export class AppRendererErrorReporter extends BaseAnalyticsReporter<AppRendererErrorParams> {
  protected readonly eventName = "app.renderer_error";

  constructor(
    params: AppRendererErrorParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
