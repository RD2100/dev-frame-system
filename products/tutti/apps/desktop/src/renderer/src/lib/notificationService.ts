import type {
  NotificationInput,
  NotificationMessage,
  NotificationService
} from "@tutti-os/ui-notifications";
import { Toast } from "./toast";

export function createToastNotificationService(): NotificationService {
  return {
    _serviceBrand: undefined,
    notify(input: NotificationMessage): void {
      notifyWithToast(input);
    },
    success(input: NotificationInput): void {
      Toast.Success(input.title, input.description);
    },
    error(input: NotificationInput): void {
      Toast.Error(input.title, input.description);
    },
    info(input: NotificationInput): void {
      Toast.tips(input.title, input.description);
    },
    warning(input: NotificationInput): void {
      Toast.tips(input.title, input.description);
    }
  };
}

function notifyWithToast(input: NotificationMessage): void {
  if (input.level === "success") {
    Toast.Success(input.title, input.description);
    return;
  }

  if (input.level === "error") {
    Toast.Error(input.title, input.description);
    return;
  }

  Toast.tips(input.title, input.description);
}
