import type {
  NotificationInput,
  NotificationLevel,
  NotificationMessage,
  NotificationService
} from "@tutti-os/ui-notifications";

export interface ForegroundNotificationPresenter {
  show(input: NotificationMessage): void;
}

export interface BackgroundNotificationPresenter {
  show(input: NotificationMessage): Promise<void> | void;
}

export interface CompositeNotificationNavigation {
  agentSessionId: string;
  provider: string;
  workspaceId: string;
}

export interface HostBackgroundNotificationsApi {
  show(input: {
    body?: string;
    level: NotificationLevel;
    navigation?: CompositeNotificationNavigation;
    title: string;
  }): Promise<unknown> | void;
}

export interface NotificationVisibilityState {
  isForeground(): boolean;
}

export interface DocumentNotificationVisibilitySource {
  hasFocus(): boolean;
  visibilityState(): DocumentVisibilityState;
}

export interface BackgroundNotificationPolicy {
  shouldNotifyInBackground(input: NotificationMessage): boolean;
}

export type CompositeNotificationPresentation =
  | "background-only"
  | "default"
  | "foreground-only";

/**
 * Desktop-side extension of the shared NotificationMessage: callers can scope
 * a message to a single face. "background-only" messages never toast (the
 * in-app surface already covers them); "foreground-only" messages never reach
 * the OS (a richer scenario-specific message owns the OS face).
 */
export interface CompositeNotificationMessage extends NotificationMessage {
  /**
   * Clicking the OS notification focuses the window and opens this agent
   * session. Forwarded over IPC as an optional payload field.
   */
  navigation?: CompositeNotificationNavigation;
  presentation?: CompositeNotificationPresentation;
}

export function createDefaultBackgroundNotificationPolicy(): BackgroundNotificationPolicy {
  return {
    shouldNotifyInBackground() {
      return true;
    }
  };
}

export function createHostBackgroundNotificationPresenter(
  hostNotificationsApi: HostBackgroundNotificationsApi
): BackgroundNotificationPresenter {
  return {
    async show(input) {
      const navigation = (input as CompositeNotificationMessage).navigation;
      await hostNotificationsApi.show({
        body: input.description,
        level: input.level,
        title: input.title,
        ...(navigation ? { navigation } : {})
      });
    }
  };
}

export function createDocumentNotificationVisibilityState(
  source: DocumentNotificationVisibilitySource
): NotificationVisibilityState {
  return {
    isForeground() {
      return source.visibilityState() === "visible" && source.hasFocus();
    }
  };
}

export function createCompositeNotificationService(input: {
  background: BackgroundNotificationPresenter;
  foreground: ForegroundNotificationPresenter;
  policy: BackgroundNotificationPolicy;
  visibility: NotificationVisibilityState;
}): NotificationService {
  const notify = (message: NotificationMessage): void => {
    const presentation = compositeNotificationPresentation(message);
    if (presentation !== "background-only") {
      input.foreground.show(message);
    }
    if (
      presentation !== "foreground-only" &&
      !input.visibility.isForeground() &&
      input.policy.shouldNotifyInBackground(message)
    ) {
      showBackgroundNotification(input.background, message);
    }
  };

  return {
    _serviceBrand: undefined,
    notify,
    success(message) {
      notifyWithLevel(notify, "success", message);
    },
    error(message) {
      notifyWithLevel(notify, "error", message);
    },
    info(message) {
      notifyWithLevel(notify, "info", message);
    },
    warning(message) {
      notifyWithLevel(notify, "warning", message);
    }
  };
}

function compositeNotificationPresentation(
  message: NotificationMessage
): CompositeNotificationPresentation {
  return (message as CompositeNotificationMessage).presentation ?? "default";
}

function showBackgroundNotification(
  background: BackgroundNotificationPresenter,
  message: NotificationMessage
): void {
  try {
    void Promise.resolve(background.show(message)).catch(() => undefined);
  } catch {
    // Background notifications are best-effort; foreground feedback already ran.
  }
}

function notifyWithLevel(
  notify: (message: NotificationMessage) => void,
  level: NotificationLevel,
  message: NotificationInput
): void {
  notify({
    ...message,
    level
  });
}
