import { proxy } from "valtio";
import type { WorkspaceCatalogStoreState } from "../workspaceCatalogTypes";
import { createInitialWorkspaceCatalogState } from "./workspaceCatalogModel.ts";

export function createWorkspaceCatalogStore(
  platform: NodeJS.Platform
): WorkspaceCatalogStoreState {
  return proxy(createInitialWorkspaceCatalogState(platform));
}
