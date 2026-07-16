import { proxy } from "valtio";
import type { AppUpdateStoreState } from "../appUpdateTypes";
import { resolveAppUpdateViewState } from "./appUpdateViewModel.ts";

export function createAppUpdateStore(): AppUpdateStoreState {
  return proxy({
    error: null,
    isActing: false,
    updateState: null,
    view: resolveAppUpdateViewState(null)
  });
}
