import { useEffect } from "react";
import { selectFocusedVisibleWorkbenchNode } from "../../core/selectors.ts";
import { useWorkbenchController } from "../WorkbenchProvider.tsx";
import {
  resolveWorkbenchShortcutIntent,
  type WorkbenchWindowManagementShortcutPreset
} from "./workbenchShortcutIntent.ts";

export function useWorkbenchShortcuts<TData = unknown>(
  options: {
    enabled?: boolean;
    windowManagementShortcutPreset?: WorkbenchWindowManagementShortcutPreset | null;
  } = {}
): void {
  const controller = useWorkbenchController<TData>();
  const enabled = options.enabled ?? true;
  const windowManagementShortcutPreset =
    options.windowManagementShortcutPreset ?? null;

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      const intent = resolveWorkbenchShortcutIntent(event, {
        windowManagementShortcutPreset
      });
      if (!intent) {
        return;
      }

      let handled = false;
      const focusedNode = selectFocusedVisibleWorkbenchNode(
        controller.getSnapshot()
      );
      if (intent.type === "exitFullscreen") {
        if (focusedNode?.displayMode === "fullscreen") {
          controller.commands.exitFullscreen(focusedNode.id);
          handled = true;
        }
      } else if (intent.type === "applyFocusedSnapTarget") {
        if (focusedNode) {
          controller.commands.applySnapTarget(
            focusedNode.id,
            intent.snapTarget
          );
          handled = true;
        }
      } else if (intent.type === "applyFocusedQuickLayout") {
        if (focusedNode) {
          controller.commands.applyQuickLayout(focusedNode.id, intent.target);
          handled = true;
        }
      } else {
        controller.commands.applyVisibleLayoutPreset(intent.preset);
        handled = true;
      }

      if (handled) {
        event.preventDefault();
        event.stopPropagation();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [controller, enabled, windowManagementShortcutPreset]);
}
