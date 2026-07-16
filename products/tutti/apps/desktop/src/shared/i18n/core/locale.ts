export const desktopLocales = ["en", "zh-CN"] as const;

export type DesktopLocale = (typeof desktopLocales)[number];

export const defaultDesktopLocale: DesktopLocale = "en";

export function isDesktopLocale(value: unknown): value is DesktopLocale {
  return (
    typeof value === "string" && desktopLocales.includes(value as DesktopLocale)
  );
}

export function normalizeDesktopLocale(
  value: string | null | undefined
): DesktopLocale | null {
  if (!value) {
    return null;
  }

  const normalized = value.trim().toLowerCase();

  if (normalized.startsWith("zh")) {
    return "zh-CN";
  }

  if (normalized.startsWith("en")) {
    return "en";
  }

  return null;
}

export function resolveDesktopLocaleFromCandidates(
  candidates: readonly (string | null | undefined)[],
  fallback: DesktopLocale = defaultDesktopLocale
): DesktopLocale {
  for (const candidate of candidates) {
    const locale = normalizeDesktopLocale(candidate);
    if (locale) {
      return locale;
    }
  }

  return fallback;
}

export function toDocumentLanguage(locale: DesktopLocale): string {
  return locale;
}
