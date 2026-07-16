import { useSyncExternalStore } from "react";

// Device-local opt-in for sending fuller agent diagnostics ("上报异常"). Kept as
// a small shared store (not a daemon-synced preference) because consent is
// per-device; both the setup wizard's prompt and the Settings → General toggle
// read and write it through here so they stay in sync.
const STORAGE_KEY = "tutti.agentDiagnosticsReporting";

const listeners = new Set<() => void>();
let enabled = readInitial();

function readInitial(): boolean {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function getAgentDiagnosticsConsent(): boolean {
  return enabled;
}

export function setAgentDiagnosticsConsent(value: boolean): void {
  if (enabled === value) {
    return;
  }
  enabled = value;
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, value ? "true" : "false");
  } catch {
    // Best-effort persistence; the in-memory value still drives this session.
  }
  for (const listener of listeners) {
    listener();
  }
}

export function subscribeAgentDiagnosticsConsent(
  listener: () => void
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React binding for the toggle / any UI that should reflect the live value. */
export function useAgentDiagnosticsConsent(): boolean {
  return useSyncExternalStore(
    subscribeAgentDiagnosticsConsent,
    getAgentDiagnosticsConsent
  );
}
