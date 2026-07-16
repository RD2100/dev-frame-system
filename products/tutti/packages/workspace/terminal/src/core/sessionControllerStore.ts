import { truncateTerminalScrollback } from "./scrollback.ts";

export interface TerminalSessionControllerState {
  contentEpoch: number;
  inputReady: boolean;
  rawOutput: string;
  surfaceError: string | null;
}

export interface TerminalSessionControllerStore {
  appendRawOutput(data: string): void;
  clearListeners(): void;
  getState(): TerminalSessionControllerState;
  replaceRawOutput(rawOutput: string): void;
  setInputReady(inputReady: boolean): void;
  setSurfaceError(surfaceError: string | null): void;
  subscribe(listener: () => void): () => void;
}

const initialState: TerminalSessionControllerState = {
  contentEpoch: 0,
  inputReady: false,
  rawOutput: "",
  surfaceError: null
};

export function createTerminalSessionControllerStore(input: {
  maxScrollbackChars: number;
}): TerminalSessionControllerStore {
  let state = initialState;
  const listeners = new Set<() => void>();

  return {
    appendRawOutput(data) {
      if (!data) {
        return;
      }
      const nextOutput = truncateTerminalScrollback(
        `${state.rawOutput}${data}`,
        {
          maxChars: input.maxScrollbackChars
        }
      );
      if (nextOutput === state.rawOutput) {
        return;
      }
      state = {
        ...state,
        rawOutput: nextOutput
      };
      emitState(listeners);
    },
    clearListeners() {
      listeners.clear();
    },
    getState() {
      return state;
    },
    replaceRawOutput(rawOutput) {
      state = {
        ...state,
        contentEpoch: state.contentEpoch + 1,
        rawOutput: truncateTerminalScrollback(rawOutput, {
          maxChars: input.maxScrollbackChars
        })
      };
      emitState(listeners);
    },
    setInputReady(inputReady) {
      if (state.inputReady === inputReady) {
        return;
      }
      state = {
        ...state,
        inputReady
      };
      emitState(listeners);
    },
    setSurfaceError(surfaceError) {
      if (state.surfaceError === surfaceError) {
        return;
      }
      state = {
        ...state,
        surfaceError
      };
      emitState(listeners);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    }
  };
}

function emitState(listeners: Set<() => void>) {
  for (const listener of listeners) {
    listener();
  }
}
