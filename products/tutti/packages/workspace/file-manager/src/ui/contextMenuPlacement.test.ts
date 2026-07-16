import assert from "node:assert/strict";
import test from "node:test";
import {
  clampContextMenuPosition,
  estimateOpenWithSubmenuHeight
} from "./contextMenuPlacement.ts";

test("clampContextMenuPosition keeps menus inside the boundary", () => {
  assert.deepEqual(
    clampContextMenuPosition({
      boundaryHeight: 400,
      boundaryWidth: 300,
      menuHeight: 120,
      menuWidth: 220,
      x: 12,
      y: 24
    }),
    { x: 12, y: 24 }
  );

  assert.deepEqual(
    clampContextMenuPosition({
      boundaryHeight: 400,
      boundaryWidth: 300,
      menuHeight: 120,
      menuWidth: 220,
      x: 200,
      y: 360
    }),
    { x: 72, y: 272 }
  );
});

test("estimateOpenWithSubmenuHeight scales with submenu sections", () => {
  assert.equal(
    estimateOpenWithSubmenuHeight({
      applicationCount: 0,
      isLoading: false,
      showExternalSection: false,
      showOpenInAppBrowser: false,
      showOpenInDefaultBrowser: false,
      showOpenWithOther: false
    }),
    16
  );

  assert.equal(
    estimateOpenWithSubmenuHeight({
      applicationCount: 6,
      isLoading: true,
      showExternalSection: true,
      showOpenInAppBrowser: true,
      showOpenInDefaultBrowser: true,
      showOpenWithOther: true
    }),
    400
  );
});
