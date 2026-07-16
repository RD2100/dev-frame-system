import { cn } from "@tutti-os/ui-system";
import { formatTuttiDateTime } from "@tutti-os/ui-system/date-format";
import { getActiveLocale, translate } from "@renderer/i18n";
import { resolveDesktopErrorMessage } from "./desktopErrors";

export { cn };

export function formatError(error: unknown): string {
  return resolveDesktopErrorMessage(error, getActiveLocale());
}

export function formatTimestamp(value: string | null): string {
  if (!value) {
    return translate("common.neverOpened");
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return formatTuttiDateTime(date, getActiveLocale());
}
