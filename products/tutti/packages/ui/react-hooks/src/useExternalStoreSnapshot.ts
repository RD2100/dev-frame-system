import { useSyncExternalStore } from "react";
import type { ExternalStoreSnapshotSource } from "./types.ts";

export function useExternalStoreSnapshot<TSnapshot>(
  source: ExternalStoreSnapshotSource<TSnapshot>
): TSnapshot {
  return useSyncExternalStore(
    (listener) => source.subscribe(listener),
    () => source.getSnapshot(),
    () => (source.getServerSnapshot ?? source.getSnapshot)()
  );
}
