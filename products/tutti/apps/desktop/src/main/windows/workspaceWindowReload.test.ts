import assert from "node:assert/strict";
import test from "node:test";
import {
  installWorkspaceWindowDevelopmentReloadShortcut,
  isWorkspaceWindowReloadShortcut,
  type WorkspaceWindowReloadShortcutEvent,
  type WorkspaceWindowReloadShortcutInput,
  type WorkspaceWindowReloadShortcutInputSource,
  type WorkspaceWindowReloadShortcutWindow
} from "./workspaceWindowReload.ts";

test("workspace window reload shortcut accepts development reload gestures", () => {
  assert.equal(
    isWorkspaceWindowReloadShortcut(input("r", { meta: true })),
    true
  );
  assert.equal(
    isWorkspaceWindowReloadShortcut(input("R", { control: true })),
    true
  );
  assert.equal(isWorkspaceWindowReloadShortcut(input("F5")), true);
});

test("workspace window reload shortcut rejects unrelated and alt-modified input", () => {
  assert.equal(
    isWorkspaceWindowReloadShortcut(input("r", { alt: true, meta: true })),
    false
  );
  assert.equal(
    isWorkspaceWindowReloadShortcut(input("w", { meta: true })),
    false
  );
});

test("development reload shortcut reloads only when enabled", () => {
  const enabled = createShortcutWindow();
  installWorkspaceWindowDevelopmentReloadShortcut(enabled.window, {
    enabled: true
  });

  enabled.dispatch(input("r", { meta: true }));

  assert.equal(enabled.preventedCount, 1);
  assert.equal(enabled.reloadCount, 1);

  const disabled = createShortcutWindow();
  installWorkspaceWindowDevelopmentReloadShortcut(disabled.window, {
    enabled: false
  });

  disabled.dispatch(input("r", { meta: true }));

  assert.equal(disabled.preventedCount, 1);
  assert.equal(disabled.reloadCount, 0);
});

function input(
  key: string,
  modifiers: Partial<
    Omit<WorkspaceWindowReloadShortcutInput, "key" | "type">
  > = {}
): WorkspaceWindowReloadShortcutInput {
  return {
    alt: false,
    control: false,
    key,
    meta: false,
    shift: false,
    type: "keyDown",
    ...modifiers
  };
}

function createShortcutWindow() {
  let listener:
    | ((
        event: WorkspaceWindowReloadShortcutEvent,
        input: WorkspaceWindowReloadShortcutInput
      ) => void)
    | null = null;
  let devtoolsOpenListener: (() => void) | null = null;
  const state = {
    devtoolsListener: null as
      | ((
          event: WorkspaceWindowReloadShortcutEvent,
          input: WorkspaceWindowReloadShortcutInput
        ) => void)
      | null,
    preventedCount: 0,
    reloadCount: 0,
    window: {
      isDestroyed() {
        return false;
      },
      webContents: {
        devToolsWebContents:
          null as WorkspaceWindowReloadShortcutInputSource | null,
        isDestroyed() {
          return false;
        },
        on(_event, nextListener) {
          if (_event === "before-input-event") {
            listener = nextListener;
            return;
          }
          devtoolsOpenListener = nextListener as () => void;
        },
        reloadIgnoringCache() {
          state.reloadCount += 1;
        }
      }
    } satisfies WorkspaceWindowReloadShortcutWindow,
    dispatch(nextInput: WorkspaceWindowReloadShortcutInput) {
      listener?.(
        {
          preventDefault() {
            state.preventedCount += 1;
          }
        },
        nextInput
      );
    },
    openDevtools() {
      state.window.webContents.devToolsWebContents = {
        on(_event, nextListener) {
          state.devtoolsListener = nextListener;
        }
      };
      devtoolsOpenListener?.();
    },
    dispatchDevtools(nextInput: WorkspaceWindowReloadShortcutInput) {
      state.devtoolsListener?.(
        {
          preventDefault() {
            state.preventedCount += 1;
          }
        },
        nextInput
      );
    }
  };
  return state;
}

test("development reload shortcut also handles devtools focus", () => {
  const target = createShortcutWindow();
  installWorkspaceWindowDevelopmentReloadShortcut(target.window, {
    enabled: true
  });

  target.openDevtools();
  target.dispatchDevtools(input("r", { meta: true }));

  assert.equal(target.preventedCount, 1);
  assert.equal(target.reloadCount, 1);
});
