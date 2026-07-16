import { useCallback, useSyncExternalStore } from "react";
import {
  getOrCreateAgentGUIConversationListQuerySnapshot,
  subscribeAgentGUIConversationListStore,
  type AgentGUIConversationListQuery
} from "./agentGuiConversationListStore";

export function useAgentGuiConversationList(
  query: AgentGUIConversationListQuery | null
) {
  const getSnapshot = useCallback(
    () => getOrCreateAgentGUIConversationListQuerySnapshot(query),
    [query]
  );

  return useSyncExternalStore(
    subscribeAgentGUIConversationListStore,
    getSnapshot,
    getSnapshot
  );
}
