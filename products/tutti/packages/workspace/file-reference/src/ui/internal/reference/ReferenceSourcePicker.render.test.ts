import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";

import type { ReferenceNode } from "../../../contracts/referenceSource.ts";
import type { ReferenceSourcePickerProps } from "./ReferenceSourcePicker.tsx";

type JsdomModule = {
  JSDOM: new (html: string) => {
    window: Window & typeof globalThis;
  };
};
type TypeScriptModule = typeof import("typescript");

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom") as JsdomModule;
const ts = require("typescript") as TypeScriptModule;

test("reference source picker renders folder nodes without the workspace folder fallback image", async () => {
  const moduleDir = dirname(fileURLToPath(import.meta.url));
  const tempDir = mkdtempSync(join(moduleDir, ".render-test-"));
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const previousHTMLElement = globalThis.HTMLElement;
  const previousNode = globalThis.Node;
  const previousElement = globalThis.Element;
  const previousActEnvironment = (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT;
  const previousView = (globalThis as { __referenceSourcePickerView?: unknown })
    .__referenceSourcePickerView;

  let root: Root | null = null;
  try {
    const componentModuleUrl = buildReferenceSourcePickerRenderModule(tempDir);
    const dom = new JSDOM('<!doctype html><div id="root"></div>');
    globalThis.window = dom.window;
    globalThis.document = dom.window.document;
    globalThis.HTMLElement = dom.window.HTMLElement;
    globalThis.Node = dom.window.Node;
    globalThis.Element = dom.window.Element;
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = true;

    const folderNode = folder("workspace-folder", "Workspace folder");
    (
      globalThis as { __referenceSourcePickerView?: unknown }
    ).__referenceSourcePickerView = createFolderOnlyView(folderNode);

    const { ReferenceSourcePicker } = (await import(componentModuleUrl)) as {
      ReferenceSourcePicker: (
        props: ReferenceSourcePickerProps
      ) => React.ReactElement | null;
    };
    const container = dom.window.document.getElementById("root");
    assert.ok(container);

    root = createRoot(container);
    await act(async () => {
      root?.render(
        createElement(ReferenceSourcePicker, {
          aggregator: {},
          copy: createCopy(),
          onClose() {},
          onConfirm() {},
          open: true,
          workspaceId: "workspace-reference-folder-icon-test"
        } as unknown as ReferenceSourcePickerProps)
      );
    });

    assert.equal(
      dom.window.document.querySelector(
        'img[src*="workspace-folder-fallback"]'
      ),
      null
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
    globalThis.Node = previousNode;
    globalThis.Element = previousElement;
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = previousActEnvironment;
    (
      globalThis as { __referenceSourcePickerView?: unknown }
    ).__referenceSourcePickerView = previousView;
    rmSync(tempDir, { force: true, recursive: true });
  }
});

function buildReferenceSourcePickerRenderModule(tempDir: string): string {
  const uiSystemUrl = writeMock(
    tempDir,
    "ui-system.mjs",
    `
      import { createElement, isValidElement } from "react";
      const h = createElement;
      function cleanProps(props = {}) {
        const {
          asChild,
          children,
          delayDuration,
          defaultLayout,
          defaultSize,
          disableDoubleClick,
          htmlFrameClassName,
          htmlTitle,
          imageAlt,
          imageFrameClassName,
          loadingIndicator,
          loadingMessage,
          messageClassName,
          minSize,
          orientation,
          panelRef,
          renderIcon,
          textClassName,
          textFrameClassName,
          viewportProps,
          withHandle,
          ...rest
        } = props;
        return rest;
      }
      function passthrough(tag) {
        return function MockComponent(props = {}) {
          return h(tag, cleanProps(props), props.children);
        };
      }
      function icon(name) {
        return function MockIcon(props = {}) {
          return h("svg", { ...cleanProps(props), "data-icon": name });
        };
      }
      export function cn(...values) {
        return values.flat().filter(Boolean).join(" ");
      }
      export const Badge = passthrough("span");
      export const Button = passthrough("button");
      export const Card = passthrough("section");
      export const CardContent = passthrough("div");
      export const CardHeader = passthrough("div");
      export const CardTitle = passthrough("h2");
      export function Input(props = {}) {
        return h("input", cleanProps(props));
      }
      export function ResizableHandle(props = {}) {
        return h("div", cleanProps(props));
      }
      export function ResizablePanel(props = {}) {
        if (typeof props.panelRef === "function") {
          props.panelRef({ resize() {} });
        }
        return h("div", cleanProps(props), props.children);
      }
      export const ResizablePanelGroup = passthrough("div");
      export function ScrollArea(props = {}) {
        return h("div", cleanProps(props), h("div", props.viewportProps ?? {}, props.children));
      }
      export const Tooltip = passthrough("span");
      export function TooltipContent(props = {}) {
        return h("span", cleanProps(props), props.children);
      }
      export function TooltipTrigger(props = {}) {
        return props.asChild && isValidElement(props.children)
          ? props.children
          : h("span", cleanProps(props), props.children);
      }
      export const ArrowRightIcon = icon("arrow-right");
      export const CheckIcon = icon("check");
      export const ChevronDownIcon = icon("chevron-down");
      export const CloseIcon = icon("close");
      export const FolderFilledIcon = icon("folder-filled");
      export const IssueIcon = icon("issue");
      export const SearchIcon = icon("search");
      export const Spinner = icon("spinner");
    `
  );
  const iconsUrl = writeMock(
    tempDir,
    "icons.mjs",
    `
      import { createElement } from "react";
      export function AddLinedIcon(props = {}) {
        return createElement("svg", { ...props, "data-icon": "add-lined" });
      }
    `
  );
  const reactHooksUrl = writeMock(
    tempDir,
    "ui-react-hooks.mjs",
    `
      export function useComposedInputValue({ value }) {
        return {
          value: value ?? "",
          onBlur() {},
          onChange() {},
          onCompositionEnd() {},
          onCompositionStart() {}
        };
      }
    `
  );
  const filePreviewUrl = writeMock(
    tempDir,
    "file-preview.mjs",
    `
      import { createElement } from "react";
      export function WorkspaceFilePreviewSurface({ emptyMessage }) {
        return createElement("div", null, emptyMessage);
      }
    `
  );
  const fileManagerUrl = writeMock(
    tempDir,
    "file-manager.mjs",
    `
      import { createElement } from "react";
      export function WorkspaceFileEntryIcon({ entry, frameClassName }) {
        if (entry.kind === "directory") {
          return createElement(
            "span",
            { className: frameClassName },
            createElement("img", {
              alt: "",
              src: "/assets/workspace-folder-fallback.png"
            })
          );
        }
        return createElement("span", { className: frameClassName });
      }
      export function WorkspaceFileManagerContextMenu() {
        return null;
      }
      export function resolveRevealInFolderLabel() {
        return "Reveal in Folder";
      }
      export function useWorkspaceFileEntryIconUrls() {
        return {
          iconUrlByCacheKey: new Map(),
          reportEntryIconViewportEnter() {},
          reportEntryIconViewportLeave() {}
        };
      }
    `
  );
  const coreUrl = writeMock(
    tempDir,
    "core.mjs",
    `
      export function base64UrlDecode(value) {
        return Buffer.from(value, "base64url").toString("utf8");
      }
      export function nodeRefKey(ref) {
        return ref.sourceId + ":" + ref.nodeId;
      }
    `
  );
  const viewUrl = writeMock(
    tempDir,
    "view.mjs",
    `
      export function useReferenceSourcePickerView() {
        return globalThis.__referenceSourcePickerView;
      }
    `
  );
  const presentationUrl = writeMock(
    tempDir,
    "presentation.mjs",
    `
      export function formatReferenceNodePathText(node) {
        return node.ref.nodeId;
      }
      export function formatReferencePreviewDateTime(value) {
        return String(value);
      }
      export function resolveReferencePreviewSizeBytes(node) {
        return node.sizeBytes ?? null;
      }
      export function resolveReferencePreviewTimestampMs(node) {
        return node.mtimeMs ?? node.createdTimeMs ?? null;
      }
    `
  );

  const componentSource = readFileSync(
    new URL("./ReferenceSourcePicker.tsx", import.meta.url),
    "utf8"
  )
    .replace(
      /import \{ useComposedInputValue \} from "@tutti-os\/ui-react-hooks";/,
      `import { useComposedInputValue } from "${reactHooksUrl}";`
    )
    .replace(
      /import \{\s*ArrowRightIcon[\s\S]*?\} from "@tutti-os\/ui-system";/,
      `import {
        ArrowRightIcon,
        Badge,
        Button,
        Card,
        CardContent,
        CardHeader,
        CardTitle,
        CheckIcon,
        ChevronDownIcon,
        CloseIcon,
        FolderFilledIcon,
        Input,
        IssueIcon,
        ResizableHandle,
        ResizablePanel,
        ResizablePanelGroup,
        ScrollArea,
        SearchIcon,
        Spinner,
        Tooltip,
        TooltipContent,
        TooltipTrigger,
        cn
      } from "${uiSystemUrl}";`
    )
    .replace(
      /import \{ AddLinedIcon \} from "@tutti-os\/ui-system\/icons";/,
      `import { AddLinedIcon } from "${iconsUrl}";`
    )
    .replace(
      /import \{\s*WorkspaceFilePreviewSurface[\s\S]*?\} from "@tutti-os\/workspace-file-preview\/react";/,
      `import { WorkspaceFilePreviewSurface } from "${filePreviewUrl}";`
    )
    .replace(
      /import \{\s*WorkspaceFileEntryIcon[\s\S]*?\} from "@tutti-os\/workspace-file-manager";/,
      `import {
        WorkspaceFileEntryIcon,
        WorkspaceFileManagerContextMenu,
        resolveRevealInFolderLabel,
        useWorkspaceFileEntryIconUrls
      } from "${fileManagerUrl}";`
    )
    .replace(
      new RegExp(
        'import \\{\\s*base64UrlDecode[\\s\\S]*?\\} from "../../../core/index\\.ts";'
      ),
      `import { base64UrlDecode, nodeRefKey } from "${coreUrl}";`
    )
    .replace(
      new RegExp(
        'import \\{\\s*useReferenceSourcePickerView[\\s\\S]*?\\} from "../../../react/internal/reference/useReferenceSourcePickerView\\.ts";'
      ),
      `import { useReferenceSourcePickerView } from "${viewUrl}";`
    )
    .replace(
      /import \{\s*formatReferenceNodePathText[\s\S]*?\} from "\.\/referenceSourcePickerPresentation\.ts";/,
      `import {
        formatReferenceNodePathText,
        formatReferencePreviewDateTime,
        resolveReferencePreviewSizeBytes,
        resolveReferencePreviewTimestampMs
      } from "${presentationUrl}";`
    );

  const transpiled = ts.transpileModule(componentSource, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true
    },
    fileName: "ReferenceSourcePicker.tsx"
  }).outputText;
  const modulePath = join(tempDir, "ReferenceSourcePicker.rendered.mjs");
  writeFileSync(modulePath, transpiled);
  return pathToFileURL(modulePath).href;
}

function writeMock(tempDir: string, fileName: string, source: string): string {
  const filePath = join(tempDir, fileName);
  writeFileSync(filePath, source);
  return pathToFileURL(filePath).href;
}

function createFolderOnlyView(node: ReferenceNode) {
  return {
    activeFilters: [],
    activeTabLabel: "Workspace",
    breadcrumb: [],
    capabilities: { filterable: false },
    childrenByKey: {},
    confirm: async () => {},
    currentEntries: [node],
    expandedKeys: {},
    filterCategories: [],
    focusedNode: null,
    getCachedOpenWithApplications: () => null,
    hasMore: false,
    isConfirming: false,
    isLoading: false,
    isLoadingMore: false,
    isLoadingTabs: false,
    isOpeningReference: false,
    isQuery: false,
    isSelectable: () => true,
    isSelected: () => false,
    listOpenWithApplications: async () => [],
    loadMore: () => {},
    loadMoreSidebarGroups: () => {},
    openNode: async () => {},
    openWithApplication: async () => {},
    openWithOtherApplication: async () => {},
    previewState: { status: "empty" },
    revealNode: async () => {},
    searchQuery: "",
    searchResults: [],
    selectGroup: () => {},
    selectedGroupKey: "workspace:root",
    selection: [],
    selectionCount: 0,
    setFilters: () => {},
    setFocusedNode: () => {},
    setSearchQuery: () => {},
    sidebarGroupsBySource: {},
    sidebarHasMoreBySource: {},
    sidebarLoadingMoreBySource: {},
    sortNodes: (nodes: readonly ReferenceNode[]) => nodes,
    tabs: [
      {
        capabilities: { paginated: false, previewable: true, searchable: true },
        label: "Workspace",
        sourceId: "workspace"
      }
    ],
    toggleNode: () => {},
    toggleSelection: () => {},
    toggleSingleSelectionAndExpand: () => {}
  };
}

function createCopy(): ReferenceSourcePickerProps["copy"] {
  return {
    t(key, params) {
      if (key === "referencePicker.selectedCount") {
        return String(params?.count ?? 0);
      }
      return key;
    }
  };
}

function folder(nodeId: string, displayName: string): ReferenceNode {
  return {
    displayName,
    hasChildren: true,
    kind: "folder",
    ref: { nodeId, sourceId: "workspace" }
  };
}
