export function toggleWorkspaceAgentMessageCenter(input: {
  onOpened?: () => void;
  open: boolean;
  setOpen: (nextOpen: boolean) => void;
}) {
  const nextOpen = !input.open;
  input.setOpen(nextOpen);
  if (nextOpen) {
    input.onOpened?.();
  }
}
