import assert from "node:assert/strict";
import test from "node:test";
import { createI18nRuntime } from "@tutti-os/ui-i18n-runtime";
import {
  createWorkbenchHostI18nRuntime,
  workbenchHostI18nResources
} from "./workbenchHostI18n.ts";

test("dock context menu show-all-windows copy names same-kind windows", () => {
  const enI18n = createWorkbenchHostI18nRuntime(
    createI18nRuntime({
      dictionaries: [workbenchHostI18nResources.en]
    })
  );
  const zhI18n = createWorkbenchHostI18nRuntime(
    createI18nRuntime({
      dictionaries: [workbenchHostI18nResources["zh-CN"]]
    })
  );

  assert.equal(
    enI18n.t("dockContextMenu.showAllWindows"),
    "Show All Similar Windows"
  );
  assert.equal(zhI18n.t("dockContextMenu.showAllWindows"), "显示所有同类窗口");
});
