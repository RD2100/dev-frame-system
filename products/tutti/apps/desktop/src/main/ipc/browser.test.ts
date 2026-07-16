import assert from "node:assert/strict";
import test from "node:test";
import { resolveDesktopBrowserPreferredColorScheme } from "./browserPreferredColorScheme.ts";

test("desktop browser preferred color scheme honors explicit theme choices", () => {
  assert.equal(
    resolveDesktopBrowserPreferredColorScheme({
      nativeShouldUseDarkColors: true,
      themeSource: "light"
    }),
    "light"
  );
  assert.equal(
    resolveDesktopBrowserPreferredColorScheme({
      nativeShouldUseDarkColors: false,
      themeSource: "dark"
    }),
    "dark"
  );
});

test("desktop browser preferred color scheme follows native theme for system source", () => {
  assert.equal(
    resolveDesktopBrowserPreferredColorScheme({
      nativeShouldUseDarkColors: true,
      themeSource: "system"
    }),
    "dark"
  );
  assert.equal(
    resolveDesktopBrowserPreferredColorScheme({
      nativeShouldUseDarkColors: false,
      themeSource: "system"
    }),
    "light"
  );
});
