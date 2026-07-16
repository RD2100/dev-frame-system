import type { WorkspaceUserProjectServiceSnapshot } from "@tutti-os/workspace-user-project/contracts";

export type WorkspaceAppUserProjectSnapshotListener = (
  snapshot: WorkspaceUserProjectServiceSnapshot
) => void;

export interface WorkspaceAppUserProjectSnapshotBridge {
  publish(snapshot: WorkspaceUserProjectServiceSnapshot): void;
  subscribe(listener: WorkspaceAppUserProjectSnapshotListener): () => void;
}

export function createWorkspaceAppUserProjectSnapshotBridge(): WorkspaceAppUserProjectSnapshotBridge {
  const listeners = new Set<WorkspaceAppUserProjectSnapshotListener>();
  let cachedSnapshot: WorkspaceUserProjectServiceSnapshot | null = null;
  let snapshotSequence = 0;

  return {
    publish(snapshot) {
      cachedSnapshot = snapshot;
      snapshotSequence += 1;
      for (const listener of listeners) {
        listener(snapshot);
      }
    },
    subscribe(listener) {
      listeners.add(listener);
      const replaySequence = snapshotSequence;
      queueMicrotask(() => {
        if (
          !listeners.has(listener) ||
          snapshotSequence !== replaySequence ||
          !cachedSnapshot
        ) {
          return;
        }
        listener(cachedSnapshot);
      });
      return () => {
        listeners.delete(listener);
      };
    }
  };
}
