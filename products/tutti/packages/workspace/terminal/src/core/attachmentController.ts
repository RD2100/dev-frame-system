import type { TerminalTransport } from "../contracts/index.ts";

export interface TerminalAttachmentController {
  attach(afterSeq?: number): Promise<void>;
  detach(): Promise<void>;
  markDetached(): void;
}

export function createTerminalAttachmentController(input: {
  clientId: string;
  sessionId: string;
  transport: Pick<TerminalTransport, "attach" | "detach">;
}): TerminalAttachmentController {
  let attached = false;
  let attachPromise: Promise<void> | null = null;
  let detachIssued = false;
  let detachPromise: Promise<void> | null = null;
  let detachRequested = false;

  const issueDetach = async () => {
    if (detachIssued || !attached) {
      return;
    }
    detachIssued = true;
    attached = false;
    await input.transport.detach({
      clientId: input.clientId,
      sessionId: input.sessionId
    });
  };

  return {
    attach(afterSeq) {
      if (attachPromise) {
        return attachPromise;
      }
      if (attached) {
        return Promise.resolve();
      }

      attachPromise = input.transport
        .attach({
          afterSeq,
          clientId: input.clientId,
          sessionId: input.sessionId
        })
        .then(async () => {
          attached = true;
          attachPromise = null;
          if (detachRequested) {
            await issueDetach();
          }
        })
        .catch((error: unknown) => {
          attachPromise = null;
          throw error;
        });

      return attachPromise;
    },
    async detach() {
      detachRequested = true;
      if (detachPromise) {
        return detachPromise;
      }
      detachPromise = Promise.resolve(attachPromise)
        .catch(() => undefined)
        .then(async () => {
          await issueDetach();
        })
        .finally(() => {
          attachPromise = null;
          detachIssued = false;
          detachPromise = null;
          detachRequested = false;
        });
      return detachPromise;
    },
    markDetached() {
      attached = false;
      attachPromise = null;
      detachIssued = false;
      detachPromise = null;
      detachRequested = false;
    }
  };
}
