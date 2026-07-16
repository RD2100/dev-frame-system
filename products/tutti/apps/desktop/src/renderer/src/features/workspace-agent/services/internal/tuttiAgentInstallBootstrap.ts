import type {
  AgentProviderStatus,
  WorkspaceAgentProvider
} from "@tutti-os/client-tuttid-ts";
import type { IAgentProviderStatusService } from "../agentProviderStatusService.interface.ts";

const tuttiAgentProvider = "tutti-agent" satisfies WorkspaceAgentProvider;
const installActionId = "install";
const bootstrapStorageKey = "tutti.agentBootstrap.tutti-agent";
const defaultFailureBackoffMs = 6 * 60 * 60 * 1000;

let attemptedInstallThisSession = false;
let bootstrapInFlight: Promise<void> | null = null;

export interface TuttiAgentInstallBootstrapOptions {
  backoffMs?: number;
  now?: () => number;
  storage?: TuttiAgentInstallBootstrapStorage | null;
}

export interface TuttiAgentInstallBootstrapStorage {
  getItem(key: string): string | null;
  removeItem(key: string): void;
  setItem(key: string, value: string): void;
}

interface BootstrapFailureState {
  failureReason?: string;
  lastAttemptAt?: number;
  lastStatus?: string;
  packageVersion?: string;
}

export function startTuttiAgentInstallBootstrap(
  service: IAgentProviderStatusService,
  options: TuttiAgentInstallBootstrapOptions = {}
): void {
  if (attemptedInstallThisSession || bootstrapInFlight) {
    return;
  }
  bootstrapInFlight = runTuttiAgentInstallBootstrap(service, options)
    .catch(() => {})
    .finally(() => {
      bootstrapInFlight = null;
    });
}

export function resetTuttiAgentInstallBootstrapForTests(): void {
  attemptedInstallThisSession = false;
  bootstrapInFlight = null;
}

export async function runTuttiAgentInstallBootstrap(
  service: IAgentProviderStatusService,
  options: TuttiAgentInstallBootstrapOptions = {}
): Promise<void> {
  const now = options.now?.() ?? Date.now();
  const storage = resolveBootstrapStorage(options.storage);
  if (
    hasRecentFailure(storage, now, options.backoffMs ?? defaultFailureBackoffMs)
  ) {
    return;
  }

  let response;
  try {
    response = await service.ensureLoaded({
      providers: [tuttiAgentProvider]
    });
  } catch (error) {
    writeBootstrapFailure(storage, {
      failureReason: error instanceof Error ? error.message : String(error),
      lastAttemptAt: now,
      lastStatus: "failed",
      packageVersion: "latest"
    });
    throw error;
  }
  const status =
    service.getStatus(tuttiAgentProvider) ??
    response?.providers.find(
      (provider) => provider.provider === tuttiAgentProvider
    ) ??
    null;
  if (!status) {
    return;
  }
  if (status.availability.status === "ready") {
    clearBootstrapFailure(storage);
    return;
  }
  if (status.availability.status !== "not_installed") {
    return;
  }
  if (service.isActionPending(tuttiAgentProvider, installActionId)) {
    return;
  }
  if (!hasInstallAction(status)) {
    return;
  }

  try {
    attemptedInstallThisSession = true;
    await service.runAction(tuttiAgentProvider, installActionId);
    clearBootstrapFailure(storage);
    await service.refresh([tuttiAgentProvider]).catch(() => {});
  } catch (error) {
    writeBootstrapFailure(storage, {
      failureReason: error instanceof Error ? error.message : String(error),
      lastAttemptAt: now,
      lastStatus: "failed",
      packageVersion: "latest"
    });
  }
}

function hasInstallAction(status: AgentProviderStatus): boolean {
  return status.actions.some((action) => action.id === installActionId);
}

function resolveBootstrapStorage(
  storage: TuttiAgentInstallBootstrapOptions["storage"]
): TuttiAgentInstallBootstrapStorage | null {
  if (storage !== undefined) {
    return storage;
  }
  return typeof localStorage === "undefined" ? null : localStorage;
}

function hasRecentFailure(
  storage: TuttiAgentInstallBootstrapStorage | null,
  now: number,
  backoffMs: number
): boolean {
  const state = readBootstrapFailure(storage);
  if (
    state?.lastStatus !== "failed" ||
    typeof state.lastAttemptAt !== "number"
  ) {
    return false;
  }
  return now - state.lastAttemptAt < backoffMs;
}

function readBootstrapFailure(
  storage: TuttiAgentInstallBootstrapStorage | null
): BootstrapFailureState | null {
  if (!storage) {
    return null;
  }
  try {
    const raw = storage.getItem(bootstrapStorageKey);
    return raw ? (JSON.parse(raw) as BootstrapFailureState) : null;
  } catch {
    return null;
  }
}

function writeBootstrapFailure(
  storage: TuttiAgentInstallBootstrapStorage | null,
  state: BootstrapFailureState
): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(bootstrapStorageKey, JSON.stringify(state));
  } catch {
    // Best-effort bootstrap metadata must never block manual setup.
  }
}

function clearBootstrapFailure(
  storage: TuttiAgentInstallBootstrapStorage | null
): void {
  if (!storage) {
    return;
  }
  try {
    storage.removeItem(bootstrapStorageKey);
  } catch {
    // Best-effort cleanup.
  }
}
