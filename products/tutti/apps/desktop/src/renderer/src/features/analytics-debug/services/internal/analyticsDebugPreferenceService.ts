import { proxy } from "valtio";
import type {
  AnalyticsDebugPreferenceStoreState,
  IAnalyticsDebugPreferenceService
} from "../analyticsDebugPreferenceService.interface";

const analyticsDebugEnabledStorageKey = "tutti.analyticsDebug.enabled";

export interface AnalyticsDebugPreferenceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface AnalyticsDebugPreferenceServiceInput {
  available: boolean;
  storage?: AnalyticsDebugPreferenceStorage;
}

export class AnalyticsDebugPreferenceService implements IAnalyticsDebugPreferenceService {
  readonly _serviceBrand: undefined;
  readonly store: AnalyticsDebugPreferenceStoreState;

  private readonly storage: AnalyticsDebugPreferenceStorage | null;

  constructor(input: AnalyticsDebugPreferenceServiceInput) {
    this.storage = input.storage ?? resolveLocalStorage();
    this.store = proxy({
      available: input.available,
      enabled: input.available ? readEnabled(this.storage) : false
    });
  }

  setEnabled(enabled: boolean): void {
    if (!this.store.available) {
      return;
    }

    this.store.enabled = enabled;
    try {
      this.storage?.setItem(
        analyticsDebugEnabledStorageKey,
        enabled ? "1" : "0"
      );
    } catch {
      // Keep the in-memory preference even when local storage is unavailable.
    }
  }
}

function readEnabled(storage: AnalyticsDebugPreferenceStorage | null): boolean {
  try {
    return storage?.getItem(analyticsDebugEnabledStorageKey) === "1";
  } catch {
    return false;
  }
}

function resolveLocalStorage(): AnalyticsDebugPreferenceStorage | null {
  if (typeof globalThis.localStorage === "undefined") {
    return null;
  }

  return globalThis.localStorage;
}
