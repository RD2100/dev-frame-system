import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { MessageCenterOpenedParams } from "./types.ts";

export class MessageCenterOpenedReporter extends BaseAnalyticsReporter<MessageCenterOpenedParams> {
  protected readonly eventName = "message_center.opened";

  constructor(
    params: MessageCenterOpenedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
