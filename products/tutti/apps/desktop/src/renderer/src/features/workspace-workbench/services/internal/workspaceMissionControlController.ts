import type {
  WorkbenchHostNodeData,
  WorkbenchMissionControlAdapter,
  WorkbenchMissionControlMode
} from "@tutti-os/workbench-surface";
import { MissionControlActivatedReporter } from "../../../analytics/reporters/mission-control-activated/missionControlActivatedReporter.ts";
import { MissionControlDeactivatedReporter } from "../../../analytics/reporters/mission-control-deactivated/missionControlDeactivatedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";

export type WorkspaceMissionControlTrigger = "button" | "keyboard";

export interface WorkspaceMissionControlOpenRequest {
  nodeIds?: readonly string[];
  trigger?: WorkspaceMissionControlTrigger;
}

export interface WorkspaceMissionControlSnapshot {
  canOpen: boolean;
  isOpen: boolean;
  mode: WorkbenchMissionControlMode | null;
  nodeIds: readonly string[] | null;
  shortcutsEnabled: boolean;
  visibleWindowCount: number;
}

export interface WorkspaceMissionControlController {
  close: () => void;
  getSnapshot: () => WorkspaceMissionControlSnapshot;
  open: (
    mode: WorkbenchMissionControlMode,
    request?:
      | WorkspaceMissionControlOpenRequest
      | WorkspaceMissionControlTrigger
  ) => void;
  setAdapter: (
    adapter: WorkbenchMissionControlAdapter<WorkbenchHostNodeData> | null
  ) => void;
  subscribe: (listener: () => void) => () => void;
}

export interface WorkspaceMissionControlControllerDependencies {
  reporterService?: Pick<IReporterService, "trackEvents">;
  reporterNow?: () => number;
}

export function createWorkspaceMissionControlController(
  dependencies: WorkspaceMissionControlControllerDependencies = {}
): WorkspaceMissionControlController {
  let adapter: WorkbenchMissionControlAdapter<WorkbenchHostNodeData> | null =
    null;
  let unsubscribeAdapter: (() => void) | null = null;
  let activatedAt: number | null = null;
  let nodeIds: readonly string[] | null = null;
  let snapshot = createSnapshot({ adapter, mode: null, nodeIds });
  const listeners = new Set<() => void>();
  const now = () => dependencies.reporterNow?.() ?? Date.now();

  const notify = () => {
    for (const listener of listeners) {
      listener();
    }
  };
  const setMode = (
    mode: WorkbenchMissionControlMode | null,
    nextNodeIds: readonly string[] | null = mode === null ? null : nodeIds
  ) => {
    nodeIds = nextNodeIds;
    const nextSnapshot = createSnapshot({ adapter, mode, nodeIds });
    if (isEqualSnapshot(snapshot, nextSnapshot)) {
      return;
    }

    snapshot = nextSnapshot;
    notify();
  };
  const refreshSnapshot = () => {
    const nextMode =
      !adapter || countVisibleNodes(adapter, nodeIds) <= 1
        ? null
        : snapshot.mode;
    if (nextMode === null) {
      nodeIds = null;
    }
    const nextSnapshot = createSnapshot({
      adapter,
      mode: nextMode,
      nodeIds
    });
    if (isEqualSnapshot(snapshot, nextSnapshot)) {
      return;
    }

    snapshot = nextSnapshot;
    notify();
  };

  return {
    close: () => {
      if (snapshot.mode === null) {
        return;
      }

      const durationMs =
        activatedAt === null ? 0 : Math.max(0, now() - activatedAt);
      setMode(null);
      activatedAt = null;
      reportDeactivated(durationMs, dependencies);
    },
    getSnapshot: () => {
      return snapshot;
    },
    open: (mode, request = "button") => {
      const normalizedRequest =
        typeof request === "string" ? { trigger: request } : request;
      const nextNodeIds = normalizedRequest.nodeIds ?? null;
      const nextSnapshot = createSnapshot({
        adapter,
        mode,
        nodeIds: nextNodeIds
      });
      if (!nextSnapshot.canOpen || isEqualSnapshot(snapshot, nextSnapshot)) {
        return;
      }

      activatedAt = now();
      setMode(mode, nextNodeIds);
      reportActivated(
        {
          mode,
          trigger: normalizedRequest.trigger ?? "button",
          windowCount: snapshot.visibleWindowCount
        },
        dependencies
      );
    },
    setAdapter: (nextAdapter) => {
      unsubscribeAdapter?.();
      adapter = nextAdapter;
      unsubscribeAdapter = nextAdapter?.subscribe(refreshSnapshot) ?? null;

      if (!adapter) {
        refreshSnapshot();
        return;
      }
      refreshSnapshot();
    },
    subscribe: (listener) => {
      listeners.add(listener);

      return () => {
        listeners.delete(listener);
      };
    }
  };
}

function reportActivated(
  params: {
    mode: WorkbenchMissionControlMode;
    trigger: WorkspaceMissionControlTrigger;
    windowCount: number;
  },
  dependencies: WorkspaceMissionControlControllerDependencies
): void {
  if (!dependencies.reporterService) {
    return;
  }

  void new MissionControlActivatedReporter(params, {
    reporterService: dependencies.reporterService,
    now: dependencies.reporterNow
  }).report();
}

function reportDeactivated(
  durationMs: number,
  dependencies: WorkspaceMissionControlControllerDependencies
): void {
  if (!dependencies.reporterService) {
    return;
  }

  void new MissionControlDeactivatedReporter(
    {
      durationMs
    },
    {
      reporterService: dependencies.reporterService,
      now: dependencies.reporterNow
    }
  ).report();
}

function createSnapshot({
  adapter,
  mode,
  nodeIds
}: {
  adapter: WorkbenchMissionControlAdapter<WorkbenchHostNodeData> | null;
  mode: WorkbenchMissionControlMode | null;
  nodeIds: readonly string[] | null;
}): WorkspaceMissionControlSnapshot {
  const visibleWindowCount = countVisibleNodes(adapter, nodeIds);
  const canOpen = visibleWindowCount > 1;
  return {
    canOpen,
    isOpen: mode !== null,
    mode,
    nodeIds,
    shortcutsEnabled: mode === null,
    visibleWindowCount
  };
}

function countVisibleNodes(
  adapter: WorkbenchMissionControlAdapter<WorkbenchHostNodeData> | null,
  nodeIds: readonly string[] | null
): number {
  const visibleNodes = adapter?.getSnapshot().visibleNodes ?? [];
  if (nodeIds === null) {
    return visibleNodes.length;
  }
  const nodeIdSet = new Set(nodeIds);
  return visibleNodes.filter((node) => nodeIdSet.has(node.id)).length;
}

function isEqualSnapshot(
  left: WorkspaceMissionControlSnapshot,
  right: WorkspaceMissionControlSnapshot
): boolean {
  return (
    left.canOpen === right.canOpen &&
    left.isOpen === right.isOpen &&
    left.mode === right.mode &&
    areEqualNodeIds(left.nodeIds, right.nodeIds) &&
    left.shortcutsEnabled === right.shortcutsEnabled &&
    left.visibleWindowCount === right.visibleWindowCount
  );
}

function areEqualNodeIds(
  left: readonly string[] | null,
  right: readonly string[] | null
): boolean {
  if (left === right) {
    return true;
  }
  if (left === null || right === null || left.length !== right.length) {
    return false;
  }
  return left.every((nodeId, index) => nodeId === right[index]);
}
