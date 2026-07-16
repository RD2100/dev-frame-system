export const desktopThemeSources = ["system", "light", "dark"] as const;

export type DesktopThemeSource = (typeof desktopThemeSources)[number];

export const desktopThemeAppearances = ["light", "dark"] as const;

export type DesktopThemeAppearance = (typeof desktopThemeAppearances)[number];

export interface DesktopThemeState {
  appearance: DesktopThemeAppearance;
  source: DesktopThemeSource;
}

export const defaultDesktopThemeSource: DesktopThemeSource = "dark";

export function isDesktopThemeSource(
  value: unknown
): value is DesktopThemeSource {
  return (
    typeof value === "string" &&
    desktopThemeSources.includes(value as DesktopThemeSource)
  );
}
