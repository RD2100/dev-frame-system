export interface CachedTerminalScreenState {
  cols: number;
  rawSnapshot: string;
  rows: number;
  serialized: string;
  sessionId: string;
}

export interface TerminalScreenStateCache {
  clear(): void;
  clearInvalidation(nodeId: string, sessionId: string): void;
  get(nodeId: string, sessionId: string): CachedTerminalScreenState | null;
  invalidate(nodeId: string, sessionId: string): void;
  isInvalidated(nodeId: string, sessionId: string): boolean;
  peek(nodeId: string): CachedTerminalScreenState | null;
  remove(nodeId: string, sessionId: string): void;
  set(nodeId: string, state: CachedTerminalScreenState): void;
}

export function createTerminalScreenStateCache(): TerminalScreenStateCache {
  const screenStateByNodeId = new Map<string, CachedTerminalScreenState>();
  const invalidatedSessionIdByNodeId = new Map<string, string>();

  const get = (
    nodeId: string,
    sessionId: string
  ): CachedTerminalScreenState | null => {
    const normalizedNodeId = normalizeId(nodeId);
    const normalizedSessionId = normalizeId(sessionId);

    if (normalizedNodeId.length === 0 || normalizedSessionId.length === 0) {
      return null;
    }

    if (
      invalidatedSessionIdByNodeId.get(normalizedNodeId) === normalizedSessionId
    ) {
      return null;
    }

    const cached = screenStateByNodeId.get(normalizedNodeId);
    if (!cached || cached.sessionId !== normalizedSessionId) {
      return null;
    }

    return cached;
  };

  const peek = (nodeId: string): CachedTerminalScreenState | null => {
    const normalizedNodeId = normalizeId(nodeId);
    if (normalizedNodeId.length === 0) {
      return null;
    }

    return screenStateByNodeId.get(normalizedNodeId) ?? null;
  };

  const set = (nodeId: string, state: CachedTerminalScreenState): void => {
    const normalizedNodeId = normalizeId(nodeId);
    const normalizedSessionId = normalizeId(state.sessionId);

    if (
      normalizedNodeId.length === 0 ||
      normalizedSessionId.length === 0 ||
      state.serialized.length === 0
    ) {
      return;
    }

    if (
      invalidatedSessionIdByNodeId.get(normalizedNodeId) === normalizedSessionId
    ) {
      invalidatedSessionIdByNodeId.delete(normalizedNodeId);
      return;
    }

    invalidatedSessionIdByNodeId.delete(normalizedNodeId);
    screenStateByNodeId.set(normalizedNodeId, {
      cols: normalizeDimension(state.cols, 80),
      rawSnapshot: state.rawSnapshot,
      rows: normalizeDimension(state.rows, 24),
      serialized: state.serialized,
      sessionId: normalizedSessionId
    });
  };

  const remove = (nodeId: string, sessionId: string): void => {
    const normalizedNodeId = normalizeId(nodeId);
    const normalizedSessionId = normalizeId(sessionId);

    if (normalizedNodeId.length === 0 || normalizedSessionId.length === 0) {
      return;
    }

    const cached = screenStateByNodeId.get(normalizedNodeId);
    if (cached?.sessionId === normalizedSessionId) {
      screenStateByNodeId.delete(normalizedNodeId);
    }

    if (
      invalidatedSessionIdByNodeId.get(normalizedNodeId) === normalizedSessionId
    ) {
      invalidatedSessionIdByNodeId.delete(normalizedNodeId);
    }
  };

  const invalidate = (nodeId: string, sessionId: string): void => {
    const normalizedNodeId = normalizeId(nodeId);
    const normalizedSessionId = normalizeId(sessionId);

    if (normalizedNodeId.length === 0 || normalizedSessionId.length === 0) {
      return;
    }

    screenStateByNodeId.delete(normalizedNodeId);
    invalidatedSessionIdByNodeId.set(normalizedNodeId, normalizedSessionId);
  };

  const isInvalidated = (nodeId: string, sessionId: string): boolean => {
    const normalizedNodeId = normalizeId(nodeId);
    const normalizedSessionId = normalizeId(sessionId);

    if (normalizedNodeId.length === 0 || normalizedSessionId.length === 0) {
      return false;
    }

    return (
      invalidatedSessionIdByNodeId.get(normalizedNodeId) === normalizedSessionId
    );
  };

  const clearInvalidation = (nodeId: string, sessionId: string): void => {
    const normalizedNodeId = normalizeId(nodeId);
    const normalizedSessionId = normalizeId(sessionId);

    if (normalizedNodeId.length === 0 || normalizedSessionId.length === 0) {
      return;
    }

    if (
      invalidatedSessionIdByNodeId.get(normalizedNodeId) !== normalizedSessionId
    ) {
      return;
    }

    invalidatedSessionIdByNodeId.delete(normalizedNodeId);
  };

  const clear = (): void => {
    screenStateByNodeId.clear();
    invalidatedSessionIdByNodeId.clear();
  };

  return {
    clear,
    clearInvalidation,
    get,
    invalidate,
    isInvalidated,
    peek,
    remove,
    set
  };
}

function normalizeId(value: string): string {
  return value.trim();
}

function normalizeDimension(value: number, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : fallback;
}
