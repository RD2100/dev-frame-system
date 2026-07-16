import type { WorkbenchAction } from "./actions.ts";
import {
  clampWorkbenchDragRect,
  clampWorkbenchRect,
  clampWorkbenchRectToVisibleArea,
  getWorkbenchFullscreenRect,
  getWorkbenchLayoutPresetFrames,
  getWorkbenchQuickLayoutRect,
  getWorkbenchSnapRect,
  normalizeWorkbenchLayoutConstraints,
  rectsEqual
} from "./geometry.ts";
import {
  focusWorkbenchStack,
  normalizeWorkbenchStack,
  removeFromWorkbenchStack
} from "./stack.ts";
import {
  defaultWorkbenchSurfaceSize,
  defaultWorkbenchLayoutConstraints,
  type WorkbenchLayoutPreset,
  type WorkbenchNode,
  type WorkbenchState
} from "./types.ts";

export function createWorkbenchInitialState<TData = unknown>(
  partial: Partial<WorkbenchState<TData>> = {}
): WorkbenchState<TData> {
  const nodes = partial.nodes ?? [];
  return {
    nodes,
    nodeStack: normalizeWorkbenchStack(nodes, partial.nodeStack ?? []),
    activeDragNodeId: partial.activeDragNodeId ?? null,
    activeResizeNodeId: partial.activeResizeNodeId ?? null,
    activeSnapTarget: partial.activeSnapTarget ?? null,
    surfaceSize: partial.surfaceSize ?? defaultWorkbenchSurfaceSize,
    layoutConstraints: normalizeWorkbenchLayoutConstraints(
      partial.layoutConstraints ?? defaultWorkbenchLayoutConstraints
    )
  };
}

export function reduceWorkbenchState<TData>(
  state: WorkbenchState<TData>,
  action: WorkbenchAction<TData>
): WorkbenchState<TData> {
  switch (action.type) {
    case "replaceState": {
      const nextState = createWorkbenchInitialState({
        ...state,
        ...action.state
      });
      if (
        state.nodes === nextState.nodes &&
        state.nodeStack === nextState.nodeStack &&
        state.activeDragNodeId === nextState.activeDragNodeId &&
        state.activeResizeNodeId === nextState.activeResizeNodeId &&
        state.activeSnapTarget === nextState.activeSnapTarget &&
        state.surfaceSize === nextState.surfaceSize &&
        layoutConstraintsEqual(
          state.layoutConstraints,
          nextState.layoutConstraints
        )
      ) {
        return state;
      }
      return nextState;
    }

    case "replaceNodes": {
      const nodeStack = normalizeWorkbenchStack(action.nodes, state.nodeStack);
      if (state.nodes === action.nodes && state.nodeStack === nodeStack) {
        return state;
      }
      return { ...state, nodes: action.nodes, nodeStack };
    }

    case "openNode": {
      const existing = state.nodes.some((node) => node.id === action.node.id);
      const nodes = existing
        ? state.nodes.map((node) =>
            node.id === action.node.id ? action.node : node
          )
        : [...state.nodes, action.node];
      return {
        ...state,
        nodes,
        nodeStack: focusWorkbenchStack(
          normalizeWorkbenchStack(nodes, state.nodeStack),
          action.node.id
        )
      };
    }

    case "closeNode":
      if (!state.nodes.some((node) => node.id === action.nodeID)) {
        return state;
      }
      return {
        ...state,
        nodes: state.nodes.filter((node) => node.id !== action.nodeID),
        nodeStack: removeFromWorkbenchStack(state.nodeStack, action.nodeID)
      };

    case "focusNode":
      if (!state.nodes.some((node) => node.id === action.nodeID)) {
        return state;
      }
      return {
        ...state,
        nodes: state.nodes.map((node) =>
          node.id === action.nodeID
            ? { ...node, isMinimized: false, minimizedAtUnixMs: null }
            : node
        ),
        nodeStack: focusWorkbenchStack(state.nodeStack, action.nodeID)
      };

    case "minimizeNode":
      return updateNode(state, action.nodeID, (node) =>
        node.isMinimized
          ? node
          : {
              ...node,
              isMinimized: true,
              minimizedAtUnixMs: Date.now()
            }
      );

    case "restoreNode":
      return updateNode(state, action.nodeID, (node) =>
        node.isMinimized
          ? { ...node, isMinimized: false, minimizedAtUnixMs: null }
          : node
      );

    case "enterFullscreen":
      return updateNode(state, action.nodeID, (node) => {
        if (node.displayMode === "fullscreen") {
          return node;
        }
        return {
          ...node,
          displayMode: "fullscreen",
          restoreFrame: node.frame,
          isMinimized: false,
          minimizedAtUnixMs: null,
          frame: getWorkbenchFullscreenRect(
            state.surfaceSize,
            state.layoutConstraints,
            node.sizeConstraints
          )
        };
      });

    case "exitFullscreen":
      return updateNode(state, action.nodeID, (node) => {
        if (node.displayMode !== "fullscreen") {
          return node;
        }
        return {
          ...node,
          displayMode: "floating",
          frame: node.restoreFrame ?? node.frame,
          restoreFrame: null
        };
      });

    case "applyQuickLayout":
      return updateNode(state, action.nodeID, (node) => {
        const frame = getWorkbenchQuickLayoutRect(
          action.target,
          state.surfaceSize,
          state.layoutConstraints,
          node.sizeConstraints
        );
        if (
          node.displayMode === "floating" &&
          !node.isMinimized &&
          node.restoreFrame === null &&
          rectsEqual(node.frame, frame)
        ) {
          return node;
        }
        return {
          ...node,
          frame,
          displayMode: "floating" as const,
          restoreFrame: null,
          isMinimized: false,
          minimizedAtUnixMs: null
        };
      });

    case "applyLayoutPreset":
      return applyLayoutPresetToNodes(state, action.nodeIDs, action.preset);

    case "applyVisibleLayoutPreset":
      return applyLayoutPresetToNodes(
        state,
        state.nodes.filter((node) => !node.isMinimized).map((node) => node.id),
        action.preset
      );

    case "applyActiveSnapTarget":
    case "applySnapTarget":
      return updateNode(state, action.nodeID, (node) => {
        const frame = getWorkbenchSnapRect(
          action.type === "applySnapTarget"
            ? action.snapTarget
            : state.activeSnapTarget,
          state.surfaceSize,
          state.layoutConstraints,
          node.sizeConstraints
        );
        if (!frame) {
          return node;
        }
        if (
          node.displayMode === "floating" &&
          !node.isMinimized &&
          node.restoreFrame === null &&
          rectsEqual(node.frame, frame)
        ) {
          return node;
        }
        return {
          ...node,
          frame,
          displayMode: "floating",
          restoreFrame: null,
          isMinimized: false,
          minimizedAtUnixMs: null
        };
      });

    case "dragNode":
      return updateNode(state, action.nodeID, (node) => {
        const frame = clampWorkbenchDragRect(
          action.frame,
          state.surfaceSize,
          state.layoutConstraints,
          node.sizeConstraints
        );
        if (rectsEqual(node.frame, frame)) {
          return node;
        }
        return {
          ...node,
          frame,
          displayMode: "floating",
          restoreFrame:
            node.displayMode === "fullscreen" ? node.restoreFrame : null
        };
      });

    case "moveNode":
    case "resizeNode":
      return updateNode(state, action.nodeID, (node) => {
        const frame = clampWorkbenchRect(
          action.frame,
          state.surfaceSize,
          state.layoutConstraints,
          node.sizeConstraints
        );
        if (rectsEqual(node.frame, frame)) {
          return node;
        }
        return {
          ...node,
          frame,
          displayMode: "floating",
          restoreFrame:
            node.displayMode === "fullscreen" ? node.restoreFrame : null
        };
      });

    case "setActiveDragNode":
      if (state.activeDragNodeId === action.nodeID) {
        return state;
      }
      return { ...state, activeDragNodeId: action.nodeID };

    case "setActiveResizeNode":
      if (state.activeResizeNodeId === action.nodeID) {
        return state;
      }
      return { ...state, activeResizeNodeId: action.nodeID };

    case "setActiveSnapTarget":
      if (state.activeSnapTarget === action.snapTarget) {
        return state;
      }
      return { ...state, activeSnapTarget: action.snapTarget };

    case "setSurfaceSize":
      if (
        state.surfaceSize.width === action.size.width &&
        state.surfaceSize.height === action.size.height
      ) {
        return state;
      }
      return {
        ...state,
        surfaceSize: action.size,
        nodes: state.nodes.map((node) =>
          node.displayMode === "fullscreen"
            ? {
                ...node,
                frame: getWorkbenchFullscreenRect(
                  action.size,
                  state.layoutConstraints,
                  node.sizeConstraints
                )
              }
            : {
                ...node,
                frame: clampWorkbenchRectToVisibleArea(
                  node.frame,
                  action.size,
                  state.layoutConstraints,
                  undefined,
                  node.sizeConstraints
                )
              }
        )
      };

    case "setLayoutConstraints": {
      const constraints = normalizeWorkbenchLayoutConstraints({
        ...state.layoutConstraints,
        ...action.constraints,
        safeArea: {
          ...state.layoutConstraints.safeArea,
          ...action.constraints.safeArea
        }
      });
      if (
        state.layoutConstraints.minWidth === constraints.minWidth &&
        state.layoutConstraints.minHeight === constraints.minHeight &&
        state.layoutConstraints.surfacePadding === constraints.surfacePadding &&
        state.layoutConstraints.safeArea.top === constraints.safeArea.top &&
        state.layoutConstraints.safeArea.right === constraints.safeArea.right &&
        state.layoutConstraints.safeArea.bottom ===
          constraints.safeArea.bottom &&
        state.layoutConstraints.safeArea.left === constraints.safeArea.left
      ) {
        return state;
      }
      return {
        ...state,
        layoutConstraints: constraints,
        nodes: state.nodes.map((node) =>
          node.displayMode === "fullscreen"
            ? {
                ...node,
                frame: getWorkbenchFullscreenRect(
                  state.surfaceSize,
                  constraints,
                  node.sizeConstraints
                )
              }
            : {
                ...node,
                frame: clampWorkbenchRectToVisibleArea(
                  node.frame,
                  state.surfaceSize,
                  constraints,
                  undefined,
                  node.sizeConstraints
                ),
                restoreFrame: node.restoreFrame
                  ? clampWorkbenchRectToVisibleArea(
                      node.restoreFrame,
                      state.surfaceSize,
                      constraints,
                      undefined,
                      node.sizeConstraints
                    )
                  : null
              }
        )
      };
    }

    case "setNodeSizeConstraints":
      return updateNode(state, action.nodeID, (node) => {
        if (
          sizeConstraintsEqual(node.sizeConstraints, action.sizeConstraints)
        ) {
          return node;
        }
        const frame =
          node.displayMode === "fullscreen"
            ? getWorkbenchFullscreenRect(
                state.surfaceSize,
                state.layoutConstraints,
                action.sizeConstraints
              )
            : clampWorkbenchRectToVisibleArea(
                node.frame,
                state.surfaceSize,
                state.layoutConstraints,
                undefined,
                action.sizeConstraints
              );
        const restoreFrame = node.restoreFrame
          ? clampWorkbenchRectToVisibleArea(
              node.restoreFrame,
              state.surfaceSize,
              state.layoutConstraints,
              undefined,
              action.sizeConstraints
            )
          : null;
        return {
          ...node,
          frame,
          restoreFrame,
          sizeConstraints: action.sizeConstraints
        };
      });
  }
}

function layoutConstraintsEqual(
  left: WorkbenchState["layoutConstraints"],
  right: WorkbenchState["layoutConstraints"]
): boolean {
  return (
    left.minWidth === right.minWidth &&
    left.minHeight === right.minHeight &&
    left.surfacePadding === right.surfacePadding &&
    left.safeArea.top === right.safeArea.top &&
    left.safeArea.right === right.safeArea.right &&
    left.safeArea.bottom === right.safeArea.bottom &&
    left.safeArea.left === right.safeArea.left
  );
}

function sizeConstraintsEqual(
  left: WorkbenchNode["sizeConstraints"],
  right: WorkbenchNode["sizeConstraints"]
): boolean {
  return (
    (left?.minWidth ?? null) === (right?.minWidth ?? null) &&
    (left?.minHeight ?? null) === (right?.minHeight ?? null)
  );
}

function updateNode<TData>(
  state: WorkbenchState<TData>,
  nodeID: string,
  update: (node: WorkbenchNode<TData>) => WorkbenchNode<TData>
): WorkbenchState<TData> {
  let changed = false;
  const nodes = state.nodes.map((node) => {
    if (node.id !== nodeID) {
      return node;
    }

    const nextNode = update(node);
    changed = changed || nextNode !== node;
    return nextNode;
  });

  if (!changed) {
    return state;
  }

  return {
    ...state,
    nodes,
    nodeStack: focusWorkbenchStack(state.nodeStack, nodeID)
  };
}

function applyLayoutPresetToNodes<TData>(
  state: WorkbenchState<TData>,
  inputNodeIDs: readonly string[],
  preset: WorkbenchLayoutPreset
): WorkbenchState<TData> {
  const nodeIDs = uniqueKnownNodeIDs(state.nodes, inputNodeIDs);
  if (nodeIDs.length === 0) {
    return state;
  }

  const frames = getWorkbenchLayoutPresetFrames(
    nodeIDs.length,
    preset,
    state.surfaceSize,
    state.layoutConstraints
  );
  if (!frames) {
    return state;
  }

  const frameByNodeID = new Map(
    nodeIDs.map((nodeID, index) => [nodeID, frames[index]] as const)
  );
  const nodes: WorkbenchNode<TData>[] = state.nodes.map((node) => {
    const frame = frameByNodeID.get(node.id);
    if (!frame) {
      return node;
    }
    const nextFrame = clampWorkbenchRect(
      frame,
      state.surfaceSize,
      state.layoutConstraints,
      node.sizeConstraints
    );
    return {
      ...node,
      frame: nextFrame,
      displayMode: "floating" as const,
      restoreFrame: null,
      isMinimized: false,
      minimizedAtUnixMs: null
    };
  });

  let nodeStack = state.nodeStack;
  for (const nodeID of nodeIDs) {
    nodeStack = focusWorkbenchStack(nodeStack, nodeID);
  }

  return { ...state, nodes, nodeStack };
}

function uniqueKnownNodeIDs<TData>(
  nodes: readonly WorkbenchNode<TData>[],
  nodeIDs: readonly string[]
): string[] {
  const knownNodeIDs = new Set(nodes.map((node) => node.id));
  const orderedNodeIDs: string[] = [];

  for (const nodeID of nodeIDs) {
    if (!knownNodeIDs.has(nodeID) || orderedNodeIDs.includes(nodeID)) {
      continue;
    }
    orderedNodeIDs.push(nodeID);
  }

  return orderedNodeIDs;
}
