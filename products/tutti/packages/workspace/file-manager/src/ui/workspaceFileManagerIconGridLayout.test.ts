import assert from "node:assert/strict";
import test from "node:test";
import {
  workspaceFileManagerIconGridFrameClassName,
  workspaceFileManagerIconGridIconClassName,
  workspaceFileManagerIconGridLayout
} from "./workspaceFileManagerIconGridLayout.ts";

test("icon grid layout leaves enough room for image thumbnails", () => {
  assert.equal(workspaceFileManagerIconGridLayout.iconSizePx, 84);
  assert.equal(workspaceFileManagerIconGridIconClassName(), "size-[84px]");
  assert.equal(workspaceFileManagerIconGridFrameClassName(), "size-[92px]");
});
