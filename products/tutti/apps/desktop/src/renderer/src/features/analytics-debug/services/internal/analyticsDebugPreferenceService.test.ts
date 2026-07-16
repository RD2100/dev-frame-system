import assert from "node:assert/strict";
import test from "node:test";
import { AnalyticsDebugPreferenceService } from "./analyticsDebugPreferenceService.ts";

test("AnalyticsDebugPreferenceService restores enabled state from local storage in dev", () => {
  const storage = createStorage({
    "tutti.analyticsDebug.enabled": "1"
  });
  const service = new AnalyticsDebugPreferenceService({
    available: true,
    storage
  });

  assert.equal(service.store.available, true);
  assert.equal(service.store.enabled, true);
});

test("AnalyticsDebugPreferenceService defaults to disabled when no cached value exists", () => {
  const service = new AnalyticsDebugPreferenceService({
    available: true,
    storage: createStorage({})
  });

  assert.equal(service.store.enabled, false);
});

test("AnalyticsDebugPreferenceService writes local storage when toggled", () => {
  const storage = createStorage({});
  const service = new AnalyticsDebugPreferenceService({
    available: true,
    storage
  });

  service.setEnabled(true);
  assert.equal(service.store.enabled, true);
  assert.equal(storage.getItem("tutti.analyticsDebug.enabled"), "1");

  service.setEnabled(false);
  assert.equal(service.store.enabled, false);
  assert.equal(storage.getItem("tutti.analyticsDebug.enabled"), "0");
});

test("AnalyticsDebugPreferenceService stays unavailable and disabled outside dev", () => {
  const storage = createStorage({
    "tutti.analyticsDebug.enabled": "1"
  });
  const service = new AnalyticsDebugPreferenceService({
    available: false,
    storage
  });

  assert.equal(service.store.available, false);
  assert.equal(service.store.enabled, false);

  service.setEnabled(true);
  assert.equal(service.store.enabled, false);
  assert.equal(storage.getItem("tutti.analyticsDebug.enabled"), "1");
});

function createStorage(initial: Record<string, string>) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key: string): string | null {
      return values.get(key) ?? null;
    },
    setItem(key: string, value: string): void {
      values.set(key, value);
    }
  };
}
