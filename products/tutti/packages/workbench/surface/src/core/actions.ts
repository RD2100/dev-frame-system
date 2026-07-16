import type {
  WorkbenchFrame,
  WorkbenchLayoutPreset,
  WorkbenchLayoutConstraintsInput,
  WorkbenchNode,
  WorkbenchNodeSizeConstraints,
  WorkbenchQuickLayoutTarget,
  WorkbenchSize,
  WorkbenchSnapTarget,
  WorkbenchState
} from "./types.ts";

export type WorkbenchAction<TData = unknown> =
  | { type: "replaceState"; state: Partial<WorkbenchState<TData>> }
  | { type: "replaceNodes"; nodes: WorkbenchNode<TData>[] }
  | { type: "openNode"; node: WorkbenchNode<TData> }
  | { type: "closeNode"; nodeID: string }
  | { type: "focusNode"; nodeID: string }
  | { type: "minimizeNode"; nodeID: string }
  | { type: "restoreNode"; nodeID: string }
  | { type: "enterFullscreen"; nodeID: string }
  | { type: "exitFullscreen"; nodeID: string }
  | {
      type: "applyQuickLayout";
      nodeID: string;
      target: WorkbenchQuickLayoutTarget;
    }
  | {
      type: "applyLayoutPreset";
      nodeIDs: string[];
      preset: WorkbenchLayoutPreset;
    }
  | {
      type: "applyVisibleLayoutPreset";
      preset: WorkbenchLayoutPreset;
    }
  | { type: "applyActiveSnapTarget"; nodeID: string }
  | {
      type: "applySnapTarget";
      nodeID: string;
      snapTarget: WorkbenchSnapTarget;
    }
  | { type: "dragNode"; nodeID: string; frame: WorkbenchFrame }
  | { type: "moveNode"; nodeID: string; frame: WorkbenchFrame }
  | { type: "resizeNode"; nodeID: string; frame: WorkbenchFrame }
  | { type: "setActiveDragNode"; nodeID: string | null }
  | { type: "setActiveResizeNode"; nodeID: string | null }
  | { type: "setActiveSnapTarget"; snapTarget: WorkbenchSnapTarget }
  | { type: "setSurfaceSize"; size: WorkbenchSize }
  | {
      type: "setLayoutConstraints";
      constraints: WorkbenchLayoutConstraintsInput;
    }
  | {
      type: "setNodeSizeConstraints";
      nodeID: string;
      sizeConstraints: WorkbenchNodeSizeConstraints | null;
    };
