import type { HTMLAttributes, JSX, ReactNode } from "react";
import { useTranslation } from "@renderer/i18n";
import { Button, PanelIcon, cn } from "@tutti-os/ui-system";

export interface DesktopAgentGUIWorkbenchHeaderProps extends HTMLAttributes<HTMLElement> {
  defaultActions?: ReactNode;
  isConversationRailAutoCollapsed: boolean;
  isConversationRailCollapsed: boolean;
  onToggleConversationRail: (nextCollapsed: boolean) => void;
  title?: string;
}

export function DesktopAgentGUIWorkbenchHeader({
  className,
  defaultActions,
  isConversationRailAutoCollapsed,
  isConversationRailCollapsed,
  onToggleConversationRail,
  title,
  ...headerProps
}: DesktopAgentGUIWorkbenchHeaderProps): JSX.Element {
  const { t } = useTranslation();
  const toggleLabel = isConversationRailCollapsed
    ? t("workspace.agentGui.expandConversationRail")
    : t("workspace.agentGui.collapseConversationRail");

  return (
    <header
      {...headerProps}
      className={cn(
        "flex h-full min-h-0 items-center justify-between gap-3 bg-[var(--background-panel)] px-2 pl-3",
        className
      )}
    >
      <div className="flex min-w-0 items-center gap-[3px]">
        <span className="min-w-0 truncate text-[13px] font-semibold leading-5 text-[var(--text-primary)]">
          {title?.trim() || t("workspace.agentGui.fallbackAgentLabel")}
        </span>
        <Button
          aria-label={toggleLabel}
          className="cursor-pointer rounded-md"
          data-agent-gui-conversation-rail-auto-collapsed={
            isConversationRailAutoCollapsed ? "true" : undefined
          }
          data-agent-gui-conversation-rail-collapsed={
            isConversationRailCollapsed ? "true" : undefined
          }
          data-testid="agent-gui-toggle-conversation-rail"
          size="icon-sm"
          title={toggleLabel}
          type="button"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation();
            onToggleConversationRail(!isConversationRailCollapsed);
          }}
          onDoubleClick={(event) => event.stopPropagation()}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <PanelIcon className="size-[18px]" />
        </Button>
      </div>
      <div
        className="flex flex-none items-center gap-1"
        onDoubleClick={(event) => event.stopPropagation()}
        onPointerDown={(event) => event.stopPropagation()}
      >
        {defaultActions}
      </div>
    </header>
  );
}
