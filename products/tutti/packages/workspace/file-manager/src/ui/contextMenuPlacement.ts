export const CONTEXT_MENU_ITEM_HEIGHT_PX = 32;
export const CONTEXT_MENU_PADDING_PX = 8;
export const CONTEXT_MENU_SUBMENU_GAP_PX = 4;

export function clampContextMenuPosition(input: {
  boundaryHeight: number;
  boundaryWidth: number;
  menuHeight: number;
  menuWidth: number;
  padding?: number;
  x: number;
  y: number;
}): { x: number; y: number } {
  const padding = input.padding ?? CONTEXT_MENU_PADDING_PX;
  const maxX = Math.max(
    padding,
    input.boundaryWidth - input.menuWidth - padding
  );
  const maxY = Math.max(
    padding,
    input.boundaryHeight - input.menuHeight - padding
  );

  return {
    x: Math.min(Math.max(input.x, padding), maxX),
    y: Math.min(Math.max(input.y, padding), maxY)
  };
}

export function estimateOpenWithSubmenuHeight(input: {
  applicationCount: number;
  isLoading: boolean;
  showExternalSection: boolean;
  showOpenInAppBrowser: boolean;
  showOpenInDefaultBrowser: boolean;
  showOpenInFileViewer?: boolean;
  showOpenWithOther: boolean;
}): number {
  let itemCount = 0;

  if (input.showOpenInFileViewer) {
    itemCount += 1;
  }
  if (input.showOpenInAppBrowser) {
    itemCount += 1;
  }
  if (input.showExternalSection) {
    itemCount += 1;
  }
  if (input.isLoading) {
    itemCount += 1;
  }
  itemCount += input.applicationCount;
  if (input.showOpenInDefaultBrowser) {
    itemCount += 1;
  }
  if (input.showOpenWithOther) {
    itemCount += 2;
  }

  return itemCount * CONTEXT_MENU_ITEM_HEIGHT_PX + CONTEXT_MENU_PADDING_PX * 2;
}
