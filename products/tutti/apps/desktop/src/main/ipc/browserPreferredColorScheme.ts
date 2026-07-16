import type { DesktopThemeSource } from "../../shared/theme/index.ts";

export type BrowserPreferredColorScheme = "dark" | "light";

export function resolveDesktopBrowserPreferredColorScheme(input: {
  nativeShouldUseDarkColors: boolean;
  themeSource: DesktopThemeSource;
}): BrowserPreferredColorScheme {
  if (input.themeSource === "dark" || input.themeSource === "light") {
    return input.themeSource;
  }

  return input.nativeShouldUseDarkColors ? "dark" : "light";
}
