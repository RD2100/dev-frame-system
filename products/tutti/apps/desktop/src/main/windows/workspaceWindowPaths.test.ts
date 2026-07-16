import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { resolvePackagedWorkspaceRendererIndexPath } from "./workspaceWindowPaths.ts";

test("packaged workspace window loads renderer index from app root", () => {
  const packagedAppPath = path.join(
    "/Applications",
    "Tutti.app",
    "Contents",
    "Resources",
    "app.asar"
  );

  assert.equal(
    resolvePackagedWorkspaceRendererIndexPath(packagedAppPath),
    path.join(packagedAppPath, "out", "renderer", "index.html")
  );
});
