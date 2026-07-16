import { resolveSuffixPrefixOverlap } from "./stringOverlap.ts";

export const defaultMaxTerminalScrollbackChars = 400_000;

export interface TerminalScrollbackOptions {
  maxChars?: number;
}

export function truncateTerminalScrollback(
  snapshot: string,
  options?: TerminalScrollbackOptions
): string {
  const maxChars = normalizeMaxChars(options?.maxChars);
  if (snapshot.length <= maxChars) {
    return snapshot;
  }

  return snapshot.slice(-maxChars);
}

export function resolveTerminalScrollbackDelta(
  previous: string,
  next: string,
  options?: TerminalScrollbackOptions
): string {
  const previousSnapshot = truncateTerminalScrollback(previous, options);
  const nextSnapshot = truncateTerminalScrollback(next, options);

  if (previousSnapshot.length === 0) {
    return nextSnapshot;
  }

  if (nextSnapshot.length === 0 || previousSnapshot === nextSnapshot) {
    return "";
  }

  if (previousSnapshot.includes(nextSnapshot)) {
    return "";
  }

  const overlap = resolveSuffixPrefixOverlap(previousSnapshot, nextSnapshot);
  return nextSnapshot.slice(overlap);
}

export function mergeTerminalScrollbackSnapshots(
  persisted: string,
  live: string,
  options?: TerminalScrollbackOptions
): string {
  const persistedSnapshot = truncateTerminalScrollback(persisted, options);
  const liveSnapshot = truncateTerminalScrollback(live, options);

  if (persistedSnapshot.length === 0) {
    return liveSnapshot;
  }

  if (liveSnapshot.length === 0) {
    return persistedSnapshot;
  }

  if (persistedSnapshot === liveSnapshot) {
    return liveSnapshot;
  }

  if (liveSnapshot.includes(persistedSnapshot)) {
    return liveSnapshot;
  }

  if (persistedSnapshot.includes(liveSnapshot)) {
    return persistedSnapshot;
  }

  const overlap = resolveSuffixPrefixOverlap(persistedSnapshot, liveSnapshot);
  return truncateTerminalScrollback(
    `${persistedSnapshot}${liveSnapshot.slice(overlap)}`,
    options
  );
}

function normalizeMaxChars(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : defaultMaxTerminalScrollbackChars;
}
