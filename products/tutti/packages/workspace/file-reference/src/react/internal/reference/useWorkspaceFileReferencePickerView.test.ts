import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { WorkspaceFileReferenceAdapter } from "../../../contracts/index.ts";
import { useWorkspaceFileReferencePickerView } from "./useWorkspaceFileReferencePickerView.ts";

type PickerView = ReturnType<typeof useWorkspaceFileReferencePickerView>;
type JsdomModule = {
  JSDOM: new (html: string) => {
    window: Window & typeof globalThis;
  };
};

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom") as JsdomModule;

test("workspace file reference picker hook does not repeat search after results render", async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>');
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const previousHTMLElement = globalThis.HTMLElement;
  const previousActEnvironment = (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT;
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;

  let root: Root | null = null;
  try {
    const container = dom.window.document.getElementById("root");
    assert.ok(container);

    let searchCount = 0;
    const adapter: WorkspaceFileReferenceAdapter = {
      async searchReferences() {
        searchCount += 1;
        return [
          {
            kind: "file",
            path: "/workspace/result.md"
          }
        ];
      }
    };
    let latestView: PickerView | null = null;

    function Harness() {
      latestView = useWorkspaceFileReferencePickerView({
        fileAdapter: adapter,
        onClose() {},
        onConfirm() {},
        open: true,
        workspaceId: "workspace-hook-search"
      });
      return null;
    }

    root = createRoot(container);
    await act(async () => {
      root?.render(createElement(Harness));
    });

    const view = requireLatestView(latestView);
    await act(async () => {
      view.setSearchQuery("nd");
      await waitMs(240);
      await settlePromises();
    });
    await act(async () => {
      await settlePromises();
      await settlePromises();
    });

    assert.equal(searchCount, 1);
    const finalView = requireLatestView(latestView);
    assert.deepEqual(
      finalView.visibleEntries.map((entry) => entry.path),
      ["/workspace/result.md"]
    );
  } finally {
    if (root) {
      await act(async () => {
        root?.unmount();
      });
    }
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
    globalThis.HTMLElement = previousHTMLElement;
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = previousActEnvironment;
  }
});

function requireLatestView(view: PickerView | null): PickerView {
  assert.ok(view);
  return view;
}

function settlePromises(): Promise<void> {
  return new Promise((resolve) => {
    setImmediate(resolve);
  });
}

function waitMs(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
