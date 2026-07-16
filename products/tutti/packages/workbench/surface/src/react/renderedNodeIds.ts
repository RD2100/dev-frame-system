import type { WorkbenchNode, WorkbenchState } from "../core/types.ts";
import type { WorkbenchKeepMinimizedNodeMounted } from "./types.ts";

export function createRenderedWorkbenchNodeIDsSelector<TData>(
  shouldKeepMinimizedNodeMounted:
    | WorkbenchKeepMinimizedNodeMounted<TData>
    | undefined = undefined
): (state: WorkbenchState<TData>) => readonly string[] {
  let previousIDs: readonly string[] | null = null;

  return (state) => {
    const nextIDs = state.nodes
      .filter((node) =>
        shouldRenderWorkbenchNode(node, shouldKeepMinimizedNodeMounted)
      )
      .map((node) => node.id);

    if (previousIDs && stringArraysEqual(previousIDs, nextIDs)) {
      return previousIDs;
    }

    previousIDs = nextIDs;
    return nextIDs;
  };
}

function shouldRenderWorkbenchNode<TData>(
  node: WorkbenchNode<TData>,
  shouldKeepMinimizedNodeMounted:
    | WorkbenchKeepMinimizedNodeMounted<TData>
    | undefined
): boolean {
  return !node.isMinimized || shouldKeepMinimizedNodeMounted?.(node) === true;
}

function stringArraysEqual(left: readonly string[], right: readonly string[]) {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((value, index) => value === right[index]);
}
