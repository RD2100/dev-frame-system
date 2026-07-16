import assert from "node:assert/strict";
import test from "node:test";
import {
  createWorkbenchInitialState,
  reduceWorkbenchState
} from "./reducer.ts";
import {
  selectFocusedVisibleWorkbenchNode,
  selectFocusedWorkbenchNode,
  selectFullscreenNodeToExitBeforeDockLaunch
} from "./selectors.ts";
import type { WorkbenchNode } from "./types.ts";

test("opens, focuses, minimizes, and restores nodes", (t) => {
  t.mock.method(Date, "now", () => 1720000000000);

  let state = createWorkbenchInitialState();
  state = reduceWorkbenchState(state, {
    type: "openNode",
    node: makeNode("a")
  });
  state = reduceWorkbenchState(state, {
    type: "openNode",
    node: makeNode("b")
  });

  assert.equal(selectFocusedWorkbenchNode(state)?.id, "b");

  state = reduceWorkbenchState(state, { type: "focusNode", nodeID: "a" });
  assert.equal(selectFocusedWorkbenchNode(state)?.id, "a");

  state = reduceWorkbenchState(state, { type: "minimizeNode", nodeID: "a" });
  assert.equal(state.nodes.find((node) => node.id === "a")?.isMinimized, true);
  assert.equal(
    state.nodes.find((node) => node.id === "a")?.minimizedAtUnixMs,
    1720000000000
  );

  state = reduceWorkbenchState(state, { type: "restoreNode", nodeID: "a" });
  assert.equal(state.nodes.find((node) => node.id === "a")?.isMinimized, false);
  assert.equal(
    state.nodes.find((node) => node.id === "a")?.minimizedAtUnixMs,
    null
  );
});

test("selects the focused visible node when the stack top is minimized", () => {
  const state = createWorkbenchInitialState({
    nodes: [
      makeNode("a"),
      {
        ...makeNode("b"),
        isMinimized: true
      }
    ],
    nodeStack: ["a", "b"]
  });

  assert.equal(selectFocusedWorkbenchNode(state)?.id, "b");
  assert.equal(selectFocusedVisibleWorkbenchNode(state)?.id, "a");
});

test("tracks active resize node separately from active drag node", () => {
  let state = createWorkbenchInitialState({ nodes: [makeNode("a")] });

  state = reduceWorkbenchState(state, {
    type: "setActiveDragNode",
    nodeID: "a"
  });
  state = reduceWorkbenchState(state, {
    type: "setActiveResizeNode",
    nodeID: "a"
  });

  assert.equal(state.activeDragNodeId, "a");
  assert.equal(state.activeResizeNodeId, "a");

  state = reduceWorkbenchState(state, {
    type: "setActiveResizeNode",
    nodeID: null
  });

  assert.equal(state.activeDragNodeId, "a");
  assert.equal(state.activeResizeNodeId, null);
});

test("enters and exits fullscreen with restore frame", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 600 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("a")],
    nodeStack: ["a"]
  });

  const originalFrame = state.nodes[0]?.frame;
  state = reduceWorkbenchState(state, { type: "enterFullscreen", nodeID: "a" });
  assert.equal(state.nodes[0]?.displayMode, "fullscreen");
  assert.deepEqual(state.nodes[0]?.restoreFrame, originalFrame);
  assert.deepEqual(state.nodes[0]?.frame, {
    x: 0,
    y: 52,
    width: 900,
    height: 548
  });

  state = reduceWorkbenchState(state, { type: "exitFullscreen", nodeID: "a" });
  assert.equal(state.nodes[0]?.displayMode, "floating");
  assert.deepEqual(state.nodes[0]?.frame, originalFrame);
});

test("applies quick layouts as floating focused windows", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 1200, height: 800 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("a")],
    nodeStack: ["a"]
  });

  state = reduceWorkbenchState(state, { type: "enterFullscreen", nodeID: "a" });
  state = reduceWorkbenchState(state, {
    type: "applyQuickLayout",
    nodeID: "a",
    target: "right"
  });

  assert.equal(state.nodes[0]?.displayMode, "floating");
  assert.equal(state.nodes[0]?.restoreFrame, null);
  assert.equal(state.nodes[0]?.isMinimized, false);
  assert.deepEqual(state.nodes[0]?.frame, {
    x: 900,
    y: 52,
    width: 300,
    height: 684
  });
  assert.equal(selectFocusedWorkbenchNode(state)?.id, "a");
});

test("keeps dragging windows at their own size until snap is applied", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 1200, height: 800 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("a")],
    nodeStack: ["a"]
  });

  state = reduceWorkbenchState(state, {
    type: "setActiveSnapTarget",
    snapTarget: "top"
  });
  state = reduceWorkbenchState(state, {
    type: "moveNode",
    nodeID: "a",
    frame: { x: 140, y: 60, width: 320, height: 220 }
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: 140,
    y: 60,
    width: 320,
    height: 220
  });

  state = reduceWorkbenchState(state, {
    type: "applyActiveSnapTarget",
    nodeID: "a"
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: 0,
    y: 52,
    width: 1200,
    height: 684
  });
});

test("allows dragged floating nodes to overflow while keeping them reachable", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 640 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("a", { x: 100, y: 120, width: 640, height: 420 })],
    nodeStack: ["a"]
  });

  state = reduceWorkbenchState(state, {
    type: "dragNode",
    nodeID: "a",
    frame: { x: -620, y: 700, width: 640, height: 420 }
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: -600,
    y: 536,
    width: 640,
    height: 420
  });
});

test("applies active snap target after an overflowing drag", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 640 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("a", { x: 100, y: 120, width: 640, height: 420 })],
    nodeStack: ["a"]
  });

  state = reduceWorkbenchState(state, {
    type: "setActiveSnapTarget",
    snapTarget: "top"
  });
  state = reduceWorkbenchState(state, {
    type: "dragNode",
    nodeID: "a",
    frame: { x: -620, y: 700, width: 640, height: 420 }
  });
  state = reduceWorkbenchState(state, {
    type: "applyActiveSnapTarget",
    nodeID: "a"
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: 0,
    y: 52,
    width: 900,
    height: 524
  });
});

test("applies an explicit snap target without activating the snap preview", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 640 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("a", { x: 100, y: 120, width: 640, height: 420 })],
    nodeStack: ["a"]
  });

  state = reduceWorkbenchState(state, {
    type: "applySnapTarget",
    nodeID: "a",
    snapTarget: "top"
  });

  assert.equal(state.activeSnapTarget, null);
  assert.deepEqual(state.nodes[0]?.frame, {
    x: 0,
    y: 52,
    width: 900,
    height: 524
  });
});

test("explicit top snap restores position even when the node is already the snap size", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 640 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("a", { x: 24, y: 88, width: 900, height: 524 })],
    nodeStack: ["a"]
  });

  state = reduceWorkbenchState(state, {
    type: "applySnapTarget",
    nodeID: "a",
    snapTarget: "top"
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: 0,
    y: 52,
    width: 900,
    height: 524
  });
});

test("selects the foreground fullscreen node to exit before dock launch", () => {
  let state = createWorkbenchInitialState({
    nodes: [makeNode("a"), makeNode("b"), makeNode("c")],
    nodeStack: ["a", "b", "c"]
  });

  state = reduceWorkbenchState(state, { type: "enterFullscreen", nodeID: "a" });
  state = reduceWorkbenchState(state, { type: "enterFullscreen", nodeID: "b" });

  assert.equal(selectFullscreenNodeToExitBeforeDockLaunch(state, "c")?.id, "b");
  assert.equal(selectFullscreenNodeToExitBeforeDockLaunch(state, "b"), null);

  state = reduceWorkbenchState(state, { type: "minimizeNode", nodeID: "b" });
  assert.equal(selectFullscreenNodeToExitBeforeDockLaunch(state, "c")?.id, "a");
});

test("updates fullscreen and floating nodes when layout constraints change", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 600 },
    nodes: [
      makeNode("floating", { x: 8, y: 8, width: 320, height: 220 }),
      makeNode("fullscreen")
    ],
    nodeStack: ["floating", "fullscreen"]
  });

  state = reduceWorkbenchState(state, {
    type: "enterFullscreen",
    nodeID: "fullscreen"
  });
  state = reduceWorkbenchState(state, {
    type: "setLayoutConstraints",
    constraints: {
      surfacePadding: 0,
      safeArea: { top: 52, bottom: 64 }
    }
  });

  assert.deepEqual(state.nodes.find((node) => node.id === "floating")?.frame, {
    x: 8,
    y: 8,
    width: 320,
    height: 220
  });
  assert.deepEqual(
    state.nodes.find((node) => node.id === "fullscreen")?.frame,
    {
      x: 0,
      y: 52,
      width: 900,
      height: 548
    }
  );
});

test("recomputes fullscreen nodes against the bottom edge when surface size changes", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 600 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("fullscreen")],
    nodeStack: ["fullscreen"]
  });

  state = reduceWorkbenchState(state, {
    type: "enterFullscreen",
    nodeID: "fullscreen"
  });
  state = reduceWorkbenchState(state, {
    type: "setSurfaceSize",
    size: { width: 960, height: 640 }
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: 0,
    y: 52,
    width: 960,
    height: 588
  });
});

test("keeps floating nodes visible near the bottom when surface size changes", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 600 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("floating", { x: 8, y: 560, width: 320, height: 220 })],
    nodeStack: ["floating"]
  });

  state = reduceWorkbenchState(state, {
    type: "setSurfaceSize",
    size: { width: 960, height: 640 }
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: 8,
    y: 536,
    width: 320,
    height: 220
  });
});

test("keeps offscreen floating nodes visible when surface size changes", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 900, height: 640 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [makeNode("floating", { x: -700, y: 700, width: 640, height: 420 })],
    nodeStack: ["floating"]
  });

  state = reduceWorkbenchState(state, {
    type: "setSurfaceSize",
    size: { width: 1200, height: 800 }
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: -600,
    y: 696,
    width: 640,
    height: 420
  });
});

test("applies a batch layout preset without touching unselected nodes", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 1000, height: 700 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [
      makeNode("a"),
      makeNode("b", { x: 120, y: 96, width: 360, height: 240 }),
      makeNode("c", { x: 240, y: 140, width: 420, height: 280 }),
      makeNode("d", { x: 640, y: 180, width: 320, height: 220 })
    ],
    nodeStack: ["a", "b", "c", "d"]
  });

  state = reduceWorkbenchState(state, {
    type: "applyLayoutPreset",
    nodeIDs: ["a", "c", "b"],
    preset: { kind: "balanced" }
  });

  assert.deepEqual(state.nodes.find((node) => node.id === "a")?.frame, {
    x: 0,
    y: 52,
    width: 573,
    height: 584
  });
  assert.deepEqual(state.nodes.find((node) => node.id === "c")?.frame, {
    x: 585,
    y: 52,
    width: 415,
    height: 286
  });
  assert.deepEqual(state.nodes.find((node) => node.id === "b")?.frame, {
    x: 585,
    y: 350,
    width: 415,
    height: 286
  });
  assert.deepEqual(state.nodes.find((node) => node.id === "d")?.frame, {
    x: 640,
    y: 180,
    width: 320,
    height: 220
  });
  assert.deepEqual(state.nodeStack.slice(-3), ["a", "c", "b"]);
});

test("applies a visible layout preset without restoring minimized nodes", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 1000, height: 700 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [
      makeNode("a"),
      makeNode("b", { x: 120, y: 96, width: 360, height: 240 }),
      {
        ...makeNode("c", { x: 240, y: 140, width: 420, height: 280 }),
        isMinimized: true,
        minimizedAtUnixMs: 1720000000000
      }
    ],
    nodeStack: ["a", "b", "c"]
  });

  state = reduceWorkbenchState(state, {
    type: "applyVisibleLayoutPreset",
    preset: { kind: "row" }
  });

  assert.deepEqual(state.nodes.find((node) => node.id === "a")?.frame, {
    x: 0,
    y: 52,
    width: 494,
    height: 584
  });
  assert.deepEqual(state.nodes.find((node) => node.id === "b")?.frame, {
    x: 506,
    y: 52,
    width: 494,
    height: 584
  });
  assert.deepEqual(state.nodes.find((node) => node.id === "c")?.frame, {
    x: 240,
    y: 140,
    width: 420,
    height: 280
  });
  assert.equal(state.nodes.find((node) => node.id === "c")?.isMinimized, true);
  assert.deepEqual(state.nodeStack.slice(-2), ["a", "b"]);
});

test("enforces node size constraints when resizing and updating constraints", () => {
  let state = createWorkbenchInitialState({
    surfaceSize: { width: 1200, height: 800 },
    layoutConstraints: {
      minWidth: 220,
      minHeight: 160,
      surfacePadding: 0,
      safeArea: { top: 52, right: 0, bottom: 64, left: 0 }
    },
    nodes: [
      makeNode(
        "a",
        { x: 80, y: 80, width: 760, height: 540 },
        {
          minHeight: 520,
          minWidth: 720
        }
      )
    ],
    nodeStack: ["a"]
  });

  state = reduceWorkbenchState(state, {
    type: "resizeNode",
    nodeID: "a",
    frame: { x: 80, y: 80, width: 320, height: 220 }
  });

  assert.deepEqual(state.nodes[0]?.frame, {
    x: 80,
    y: 80,
    width: 720,
    height: 520
  });

  state = reduceWorkbenchState(state, {
    type: "setNodeSizeConstraints",
    nodeID: "a",
    sizeConstraints: { minHeight: 600, minWidth: 840 }
  });

  assert.deepEqual(state.nodes[0]?.sizeConstraints, {
    minHeight: 600,
    minWidth: 840
  });
  assert.deepEqual(state.nodes[0]?.frame, {
    x: 80,
    y: 80,
    width: 840,
    height: 600
  });
});

test("preserves state object on no-op actions", () => {
  const state = createWorkbenchInitialState({ nodes: [makeNode("a")] });
  assert.equal(
    reduceWorkbenchState(state, { type: "closeNode", nodeID: "missing" }),
    state
  );
});

test("replaces nodes and stack together", () => {
  const state = createWorkbenchInitialState({
    nodes: [makeNode("a")],
    nodeStack: ["a"]
  });
  const next = reduceWorkbenchState(state, {
    type: "replaceState",
    state: {
      nodes: [makeNode("b"), makeNode("c")],
      nodeStack: ["c", "b"]
    }
  });

  assert.deepEqual(
    next.nodes.map((node) => node.id),
    ["b", "c"]
  );
  assert.deepEqual(next.nodeStack, ["c", "b"]);
});

test("replaceState preserves existing layout constraints when omitted", () => {
  let state = createWorkbenchInitialState();
  state = reduceWorkbenchState(state, {
    type: "setLayoutConstraints",
    constraints: { surfacePadding: 0, safeArea: { top: 52, bottom: 64 } }
  });

  const next = reduceWorkbenchState(state, {
    type: "replaceState",
    state: { nodes: [makeNode("a")], nodeStack: ["a"] }
  });

  assert.deepEqual(next.layoutConstraints.safeArea, {
    top: 52,
    right: 0,
    bottom: 64,
    left: 0
  });
});

test("replaceState can update layout constraints", () => {
  const state = createWorkbenchInitialState();

  const next = reduceWorkbenchState(state, {
    type: "replaceState",
    state: {
      layoutConstraints: {
        minWidth: 280,
        minHeight: 180,
        surfacePadding: 0,
        safeArea: { top: 52, right: 0, bottom: 72, left: 0 }
      }
    }
  });

  assert.notEqual(next, state);
  assert.equal(next.layoutConstraints.minWidth, 280);
  assert.deepEqual(next.layoutConstraints.safeArea, {
    top: 52,
    right: 0,
    bottom: 72,
    left: 0
  });
});

function makeNode(
  id: string,
  frame: WorkbenchNode["frame"] = { x: 32, y: 32, width: 320, height: 220 },
  sizeConstraints: WorkbenchNode["sizeConstraints"] = null
): WorkbenchNode {
  return {
    id,
    kind: "test",
    title: id,
    frame,
    displayMode: "floating",
    restoreFrame: null,
    isMinimized: false,
    sizeConstraints,
    data: null
  };
}
