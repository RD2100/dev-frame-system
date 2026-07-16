export interface WindowCloseRequestTracker {
  readonly isClosing: boolean;
  begin(): void;
  finish(): void;
}

export function createWindowCloseRequestTracker(): WindowCloseRequestTracker {
  let isClosing = false;

  return {
    get isClosing() {
      return isClosing;
    },
    begin() {
      isClosing = true;
    },
    finish() {
      isClosing = false;
    }
  };
}
