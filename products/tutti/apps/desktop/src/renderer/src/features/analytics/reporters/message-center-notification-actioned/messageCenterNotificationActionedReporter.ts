import {
  BaseAnalyticsReporter,
  type AnalyticsReporterDependencies
} from "../baseReporter.ts";
import type { MessageCenterNotificationActionedParams } from "./types.ts";

export class MessageCenterNotificationActionedReporter extends BaseAnalyticsReporter<MessageCenterNotificationActionedParams> {
  protected readonly eventName = "message_center.notification_actioned";

  constructor(
    params: MessageCenterNotificationActionedParams,
    dependencies: AnalyticsReporterDependencies
  ) {
    super(params, dependencies);
  }
}
