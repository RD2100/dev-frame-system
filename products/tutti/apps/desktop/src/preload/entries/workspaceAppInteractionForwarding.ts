const workspaceAppGuestInteractionHostChannel =
  "browser-node:guest-interaction";

export type WorkspaceAppGuestInteractionType =
  | "focusin"
  | "keydown"
  | "pointerdown";

export interface WorkspaceAppGuestInteractionPayload {
  type: WorkspaceAppGuestInteractionType;
}

export function installWorkspaceAppInteractionForwarding({
  scope,
  sendToHost
}: {
  scope: Window;
  sendToHost: (
    channel: string,
    payload: WorkspaceAppGuestInteractionPayload
  ) => void;
}): () => void {
  const document = scope.document;
  const records: Array<{
    listener: EventListener;
    type: WorkspaceAppGuestInteractionType;
  }> = [];

  for (const type of ["pointerdown", "focusin", "keydown"] as const) {
    const listener: EventListener = () => {
      sendToHost(workspaceAppGuestInteractionHostChannel, { type });
    };
    records.push({ listener, type });
    document.addEventListener(type, listener, {
      capture: true,
      passive: true
    });
  }

  return () => {
    for (const record of records) {
      document.removeEventListener(record.type, record.listener, {
        capture: true
      });
    }
  };
}
