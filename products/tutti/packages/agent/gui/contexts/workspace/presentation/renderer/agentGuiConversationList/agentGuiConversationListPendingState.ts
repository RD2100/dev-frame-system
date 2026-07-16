const pendingCreateConversationIdsByQueryKey = new Map<
  string,
  Map<string, string>
>();
const pendingSubmitConversationIdsByQueryKey = new Map<string, Set<string>>();

export function markAgentGUIConversationCreatePendingState(input: {
  queryKey: string | null;
  ownerKey: string;
  conversationId: string;
}): boolean {
  const ownerKey = input.ownerKey.trim();
  const conversationId = input.conversationId.trim();
  if (!input.queryKey || !ownerKey || !conversationId) {
    return false;
  }
  const pendingIds =
    pendingCreateConversationIdsByQueryKey.get(input.queryKey) ??
    new Map<string, string>();
  if (pendingIds.get(ownerKey) === conversationId) {
    return false;
  }
  pendingIds.set(ownerKey, conversationId);
  pendingCreateConversationIdsByQueryKey.set(input.queryKey, pendingIds);
  return true;
}

export function clearAgentGUIConversationCreatePendingState(input: {
  queryKey: string | null;
  ownerKey: string;
  conversationId?: string | null;
}): boolean {
  const ownerKey = input.ownerKey.trim();
  if (!input.queryKey || !ownerKey) {
    return false;
  }
  const expectedConversationId = input.conversationId?.trim() ?? "";
  const pendingIds = pendingCreateConversationIdsByQueryKey.get(input.queryKey);
  const currentConversationId = pendingIds?.get(ownerKey)?.trim() ?? "";
  if (!currentConversationId) {
    return false;
  }
  if (
    expectedConversationId &&
    currentConversationId !== expectedConversationId
  ) {
    return false;
  }
  pendingIds?.delete(ownerKey);
  if (!pendingIds || pendingIds.size === 0) {
    pendingCreateConversationIdsByQueryKey.delete(input.queryKey);
  }
  return true;
}

export function getAgentGUIConversationCreatePendingState(input: {
  queryKey: string | null;
  ownerKey: string;
}): string | null {
  const ownerKey = input.ownerKey.trim();
  if (!input.queryKey || !ownerKey) {
    return null;
  }
  return (
    pendingCreateConversationIdsByQueryKey.get(input.queryKey)?.get(ownerKey) ??
    null
  );
}

export function markAgentGUIConversationSubmitPendingState(input: {
  queryKey: string | null;
  conversationId: string;
}): boolean {
  const conversationId = input.conversationId.trim();
  if (!input.queryKey || !conversationId) {
    return false;
  }
  const pendingIds =
    pendingSubmitConversationIdsByQueryKey.get(input.queryKey) ??
    new Set<string>();
  if (pendingIds.has(conversationId)) {
    return false;
  }
  pendingIds.add(conversationId);
  pendingSubmitConversationIdsByQueryKey.set(input.queryKey, pendingIds);
  return true;
}

export function clearAgentGUIConversationSubmitPendingState(input: {
  queryKey: string | null;
  conversationId: string;
}): boolean {
  const conversationId = input.conversationId.trim();
  if (!input.queryKey || !conversationId) {
    return false;
  }
  const pendingIds = pendingSubmitConversationIdsByQueryKey.get(input.queryKey);
  if (!pendingIds?.has(conversationId)) {
    return false;
  }
  pendingIds.delete(conversationId);
  if (pendingIds.size === 0) {
    pendingSubmitConversationIdsByQueryKey.delete(input.queryKey);
  }
  return true;
}

export function getAgentGUIConversationSubmitPendingState(input: {
  queryKey: string | null;
  conversationId: string | null | undefined;
}): boolean {
  const conversationId = input.conversationId?.trim() ?? "";
  if (!input.queryKey || !conversationId) {
    return false;
  }
  return (
    pendingSubmitConversationIdsByQueryKey
      .get(input.queryKey)
      ?.has(conversationId) ?? false
  );
}

export function resetAgentGUIConversationPendingStateForTests(): void {
  pendingCreateConversationIdsByQueryKey.clear();
  pendingSubmitConversationIdsByQueryKey.clear();
}
