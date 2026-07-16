import {
  getTuttidProtocolErrorCode,
  normalizeTuttidError,
  type TuttidClient
} from "@tutti-os/client-tuttid-ts";
import type {
  TerminalCloseGuardResult,
  TerminalCloseGuardService,
  TerminalDataEvent,
  TerminalDropInputResolver,
  TerminalExitEvent,
  TerminalLaunchInput,
  TerminalLaunchService,
  TerminalLinkHandler,
  TerminalMetadataEvent,
  TerminalNodeExternalState,
  TerminalSessionDescriptor,
  TerminalSnapshot,
  TerminalStateEvent,
  TerminalTransport,
  TerminalTransportAttachInput,
  TerminalTransportDetachInput,
  TerminalTransportResizeInput,
  TerminalTransportSnapshotInput,
  TerminalTransportWriteInput
} from "@tutti-os/workspace-terminal/contracts";
import type {
  DesktopHostFilesApi,
  DesktopPlatformApi,
  DesktopRuntimeApi
} from "@preload/types";
import { logDesktopTerminalEvent } from "../desktopTerminalLogging.ts";

export interface DesktopWorkspaceTerminalAdapter {
  closeGuard: TerminalCloseGuardService;
  dropInput: TerminalDropInputResolver;
  externalStateSource: {
    get(sessionId: string | null): TerminalNodeExternalState | null;
    subscribe(listener: () => void): () => void;
  };
  launchService: TerminalLaunchService;
  linkHandler: TerminalLinkHandler;
  transport: TerminalTransport;
}

interface ManagedTerminalSocket {
  clientId: string | null;
  socket: WebSocket;
}

export interface CreateDesktopWorkspaceTerminalAdapterInput {
  hostFilesApi: DesktopHostFilesApi;
  tuttidClient: TuttidClient;
  openBrowserUrl?: (request: {
    reuseIfOpen?: boolean;
    source?: "terminal";
    url: string;
    workspaceId: string;
  }) => Promise<boolean> | boolean;
  platformApi: Pick<DesktopPlatformApi, "resolveDroppedPaths">;
  runtimeApi: DesktopRuntimeApi;
  terminalTitle: string;
  workspaceId: string;
}

type Listener<TEvent> = (event: TEvent) => void;

export function createDesktopWorkspaceTerminalAdapter({
  hostFilesApi,
  tuttidClient,
  openBrowserUrl,
  platformApi,
  runtimeApi,
  terminalTitle,
  workspaceId
}: CreateDesktopWorkspaceTerminalAdapterInput): DesktopWorkspaceTerminalAdapter {
  const sessionState = new Map<string, TerminalNodeExternalState>();
  const stateListeners = new Set<() => void>();
  const dataListeners = new Set<Listener<TerminalDataEvent>>();
  const exitListeners = new Set<Listener<TerminalExitEvent>>();
  const metadataListeners = new Set<Listener<TerminalMetadataEvent>>();
  const transportStateListeners = new Set<Listener<TerminalStateEvent>>();
  const sockets = new Map<string, ManagedTerminalSocket>();
  const missingSessionIds = new Set<string>();

  const notifyStateChanged = () => {
    for (const listener of stateListeners) {
      listener();
    }
  };

  const rememberSession = (session: TerminalSessionDescriptor) => {
    missingSessionIds.delete(session.sessionId);
    sessionState.set(session.sessionId, {
      createdAt: null,
      cwd: session.cwd,
      endedAt: null,
      host: null,
      lastError: null,
      profileId: session.profileId,
      runtimeKind: session.runtimeKind,
      sessionId: session.sessionId,
      status: session.status,
      title: session.title,
      updatedAt: null
    });
    notifyStateChanged();
  };

  const updateSessionState = (
    sessionId: string,
    patch: Partial<TerminalNodeExternalState>
  ) => {
    const current = sessionState.get(sessionId) ?? {
      createdAt: null,
      cwd: null,
      endedAt: null,
      host: null,
      lastError: null,
      profileId: null,
      runtimeKind: "local",
      sessionId,
      status: "created",
      title: terminalTitle,
      updatedAt: null
    };
    sessionState.set(sessionId, {
      ...current,
      ...patch,
      sessionId
    });
    notifyStateChanged();
  };

  const markSessionMissing = (sessionId: string) => {
    missingSessionIds.add(sessionId);
    sockets.get(sessionId)?.socket.close();
    sockets.delete(sessionId);
    updateSessionState(sessionId, {
      endedAt: new Date().toISOString(),
      lastError: null,
      status: "failed"
    });
  };

  const transport: TerminalTransport = {
    async attach(input: TerminalTransportAttachInput) {
      logDesktopTerminalEvent({
        details: {
          afterSeq: input.afterSeq ?? null,
          clientId: input.clientId ?? null
        },
        event: "transport.attach.start",
        level: "info",
        runtimeApi,
        sessionId: input.sessionId,
        workspaceId
      });
      sockets.get(input.sessionId)?.socket.close();

      try {
        const session = await tuttidClient.getWorkspaceTerminal(
          workspaceId,
          input.sessionId
        );
        rememberSession(toTerminalSessionDescriptor(session));
      } catch {
        // Let the WebSocket attach path surface the authoritative attach error.
      }

      const socket = new WebSocket(
        await runtimeApi.getTerminalStreamUrl({
          afterSeq: input.afterSeq,
          sessionId: input.sessionId,
          workspaceId
        })
      );
      const managedSocket: ManagedTerminalSocket = {
        clientId: input.clientId ?? null,
        socket
      };
      sockets.set(input.sessionId, managedSocket);

      socket.addEventListener("message", (event) => {
        if (sockets.get(input.sessionId)?.socket !== socket) {
          return;
        }
        const frame = parseTerminalWebSocketFrame(event.data);
        if (!frame || frame.sessionId !== input.sessionId) {
          return;
        }
        switch (frame.type) {
          case "output":
            dataListeners.forEach((listener) =>
              listener({
                data: frame.data ?? "",
                seq: frame.seq,
                sessionId: frame.sessionId
              })
            );
            break;
          case "state":
            logDesktopTerminalEvent({
              details: {
                error: frame.error ?? null,
                status: frame.status ?? "running"
              },
              event: "transport.frame.state",
              level:
                frame.error != null || frame.status === "failed"
                  ? "warn"
                  : "info",
              runtimeApi,
              sessionId: frame.sessionId,
              workspaceId
            });
            updateSessionState(frame.sessionId, {
              lastError: frame.error ?? null,
              status: frame.status ?? "running"
            });
            transportStateListeners.forEach((listener) =>
              listener({
                error: frame.error ?? null,
                gapEndSeq: null,
                gapStartSeq: null,
                sessionId: frame.sessionId,
                status: frame.status ?? "running"
              })
            );
            break;
          case "metadata":
            logDesktopTerminalEvent({
              details: {
                cwd: frame.cwd ?? null,
                profileId: frame.profileId ?? null,
                runtimeKind: frame.runtimeKind ?? null,
                title: frame.title ?? null
              },
              event: "transport.frame.metadata",
              level: "debug",
              runtimeApi,
              sessionId: frame.sessionId,
              workspaceId
            });
            updateSessionState(frame.sessionId, {
              cwd: frame.cwd ?? undefined,
              profileId: frame.profileId ?? undefined,
              runtimeKind: frame.runtimeKind ?? undefined,
              title: frame.title ?? undefined
            });
            metadataListeners.forEach((listener) =>
              listener({
                cwd: frame.cwd ?? null,
                profileId: frame.profileId ?? null,
                runtimeKind: frame.runtimeKind,
                sessionId: frame.sessionId,
                title: frame.title ?? null
              })
            );
            break;
          case "exit":
            logDesktopTerminalEvent({
              details: {
                code: frame.code ?? null,
                error: frame.error ?? null,
                signal: frame.signal ?? null,
                status: frame.status ?? "exited"
              },
              event: "transport.frame.exit",
              level: "info",
              runtimeApi,
              sessionId: frame.sessionId,
              workspaceId
            });
            updateSessionState(frame.sessionId, {
              endedAt: new Date().toISOString(),
              lastError: frame.error ?? null,
              status: frame.status ?? "exited"
            });
            exitListeners.forEach((listener) =>
              listener({
                code: frame.code ?? null,
                reason: frame.error ?? null,
                sessionId: frame.sessionId,
                signal: frame.signal ?? null
              })
            );
            break;
          case "error":
            logDesktopTerminalEvent({
              details: {
                error: frame.error ?? null
              },
              event: "transport.frame.error",
              level: "error",
              runtimeApi,
              sessionId: frame.sessionId,
              workspaceId
            });
            updateSessionState(frame.sessionId, {
              lastError: frame.error ?? null,
              status: "failed"
            });
            transportStateListeners.forEach((listener) =>
              listener({
                error: frame.error ?? null,
                gapEndSeq: null,
                gapStartSeq: null,
                sessionId: frame.sessionId,
                status: "failed"
              })
            );
            break;
          case "gap":
            logDesktopTerminalEvent({
              details: {
                fromSeq: frame.fromSeq ?? null,
                toSeq: frame.toSeq ?? null
              },
              event: "transport.frame.gap",
              level: "warn",
              runtimeApi,
              sessionId: frame.sessionId,
              workspaceId
            });
            transportStateListeners.forEach((listener) =>
              listener({
                error: null,
                gapEndSeq: frame.toSeq ?? null,
                gapStartSeq: frame.fromSeq ?? null,
                sessionId: frame.sessionId,
                status: sessionState.get(frame.sessionId)?.status ?? "running"
              })
            );
            break;
        }
      });

      socket.addEventListener("close", (event) => {
        const isCurrentSocket = sockets.get(input.sessionId)?.socket === socket;
        logDesktopTerminalEvent({
          details: {
            code: event.code,
            reason: event.reason || null,
            wasClean: event.wasClean
          },
          event: "transport.attach.close",
          level: "info",
          runtimeApi,
          sessionId: input.sessionId,
          workspaceId
        });
        if (isCurrentSocket) {
          sockets.delete(input.sessionId);
          const currentStatus =
            sessionState.get(input.sessionId)?.status ?? "running";
          if (currentStatus !== "exited" && currentStatus !== "failed") {
            updateSessionState(input.sessionId, {
              status: "detached"
            });
            transportStateListeners.forEach((listener) =>
              listener({
                error: null,
                gapEndSeq: null,
                gapStartSeq: null,
                sessionId: input.sessionId,
                status: "detached"
              })
            );
          }
        }
      });

      try {
        await waitForWebSocketOpen(socket);
        logDesktopTerminalEvent({
          event: "transport.attach.open",
          level: "info",
          runtimeApi,
          sessionId: input.sessionId,
          workspaceId
        });
      } catch (error) {
        logDesktopTerminalEvent({
          details: {
            error: errorMessage(error)
          },
          event: "transport.attach.error",
          level: "error",
          runtimeApi,
          sessionId: input.sessionId,
          workspaceId
        });
        throw error;
      }
    },
    detach(input: TerminalTransportDetachInput) {
      const managedSocket = sockets.get(input.sessionId);
      if (!managedSocket) {
        return Promise.resolve();
      }
      if (
        input.clientId !== undefined &&
        managedSocket.clientId !== input.clientId
      ) {
        return Promise.resolve();
      }
      sockets.delete(input.sessionId);
      if (managedSocket.socket.readyState === WebSocket.OPEN) {
        managedSocket.socket.send(JSON.stringify({ type: "detach" }));
      }
      managedSocket.socket.close();
      return Promise.resolve();
    },
    onData(listener) {
      dataListeners.add(listener);
      return () => dataListeners.delete(listener);
    },
    onExit(listener) {
      exitListeners.add(listener);
      return () => exitListeners.delete(listener);
    },
    onMetadata(listener) {
      metadataListeners.add(listener);
      return () => metadataListeners.delete(listener);
    },
    onState(listener) {
      transportStateListeners.add(listener);
      return () => transportStateListeners.delete(listener);
    },
    async resize(input: TerminalTransportResizeInput) {
      if (missingSessionIds.has(input.sessionId)) {
        return;
      }
      const managedSocket = sockets.get(input.sessionId);
      if (managedSocket?.socket.readyState === WebSocket.OPEN) {
        managedSocket.socket.send(
          JSON.stringify({
            cols: input.cols,
            rows: input.rows,
            type: "resize"
          })
        );
        return;
      }
      try {
        await tuttidClient.resizeWorkspaceTerminal(
          workspaceId,
          input.sessionId,
          {
            cols: input.cols,
            rows: input.rows
          }
        );
      } catch (error) {
        if (isMissingTerminalError(error)) {
          markSessionMissing(input.sessionId);
          return;
        }
        throw error;
      }
    },
    async snapshot(
      input: TerminalTransportSnapshotInput
    ): Promise<TerminalSnapshot> {
      logDesktopTerminalEvent({
        event: "transport.snapshot.start",
        level: "info",
        runtimeApi,
        sessionId: input.sessionId,
        workspaceId
      });
      try {
        const snapshot = await tuttidClient.getWorkspaceTerminalSnapshot(
          workspaceId,
          input.sessionId
        );
        logDesktopTerminalEvent({
          details: {
            dataBytes: snapshot.data.length,
            fromSeq: snapshot.fromSeq ?? null,
            toSeq: snapshot.toSeq ?? null,
            truncated: snapshot.truncated ?? false
          },
          event: "transport.snapshot.complete",
          level: "info",
          runtimeApi,
          sessionId: input.sessionId,
          workspaceId
        });
        return snapshot;
      } catch (error) {
        logDesktopTerminalEvent({
          details: {
            error: errorMessage(error)
          },
          event: "transport.snapshot.error",
          level: "error",
          runtimeApi,
          sessionId: input.sessionId,
          workspaceId
        });
        updateSessionState(input.sessionId, {
          lastError: errorMessage(error),
          status: "failed"
        });
        throw error;
      }
    },
    write(input: TerminalTransportWriteInput) {
      const managedSocket = sockets.get(input.sessionId);
      if (
        !managedSocket ||
        managedSocket.socket.readyState !== WebSocket.OPEN
      ) {
        throw new Error("Terminal transport is not attached.");
      }
      managedSocket.socket.send(
        JSON.stringify({
          data:
            input.encoding === "binary"
              ? encodeBinaryWebSocketPayload(input.data)
              : input.data,
          encoding: input.encoding,
          type: "input"
        })
      );
      return Promise.resolve();
    }
  };

  return {
    closeGuard: {
      async check(input) {
        if (missingSessionIds.has(input.sessionId)) {
          return {
            leaderCommand: null,
            reason: "not-running",
            requiresConfirmation: false,
            status: "failed"
          } satisfies TerminalCloseGuardResult;
        }
        try {
          const guard = await tuttidClient.checkWorkspaceTerminalCloseGuard(
            workspaceId,
            input.sessionId
          );
          return {
            leaderCommand: guard.leaderCommand,
            reason: guard.reason,
            requiresConfirmation: guard.requiresConfirmation,
            status: guard.status
          } satisfies TerminalCloseGuardResult;
        } catch (error) {
          if (isMissingTerminalError(error)) {
            markSessionMissing(input.sessionId);
            return {
              leaderCommand: null,
              reason: "not-running",
              requiresConfirmation: false,
              status: "failed"
            } satisfies TerminalCloseGuardResult;
          }
          throw error;
        }
      }
    },
    dropInput(input) {
      const paths = platformApi.resolveDroppedPaths(
        Array.from(input.dataTransfer.files)
      );
      if (paths.length > 0) {
        return `${paths.map(shellQuote).join(" ")} `;
      }
      const text = input.dataTransfer.getData("text/plain").trim();
      return text ? `${text} ` : null;
    },
    externalStateSource: {
      get(sessionId) {
        return sessionId ? (sessionState.get(sessionId) ?? null) : null;
      },
      subscribe(listener) {
        stateListeners.add(listener);
        return () => stateListeners.delete(listener);
      }
    },
    launchService: {
      async create(input: TerminalLaunchInput) {
        const session = await tuttidClient.createWorkspaceTerminal(
          workspaceId,
          {
            cwd: input.cwd,
            initialInput: input.initialInput,
            profileId: input.profileId
          }
        );
        const descriptor = toTerminalSessionDescriptor(session);
        rememberSession(descriptor);
        return descriptor;
      },
      async get(sessionId) {
        try {
          const session = await tuttidClient.getWorkspaceTerminal(
            workspaceId,
            sessionId
          );
          const descriptor = toTerminalSessionDescriptor(session);
          rememberSession(descriptor);
          return descriptor;
        } catch {
          return null;
        }
      },
      async terminate(input) {
        const session = await tuttidClient.terminateWorkspaceTerminal(
          workspaceId,
          input.sessionId
        );
        rememberSession(toTerminalSessionDescriptor(session));
      }
    },
    linkHandler: {
      async open(target) {
        if (target.path) {
          await hostFilesApi.openTerminalLink({
            column: target.column,
            cwd: target.cwd ?? null,
            line: target.line,
            path: target.path,
            workspaceID: workspaceId
          });
          return;
        }
        if (target.url) {
          let openedInWorkspaceBrowser: boolean;
          try {
            openedInWorkspaceBrowser =
              (await openBrowserUrl?.({
                reuseIfOpen: true,
                source: "terminal",
                url: target.url,
                workspaceId
              })) === true;
          } catch {
            openedInWorkspaceBrowser = false;
          }
          if (openedInWorkspaceBrowser) {
            return;
          }
          await hostFilesApi.openExternal(target.url);
        }
      }
    },
    transport
  };
}

function isMissingTerminalError(error: unknown): boolean {
  const normalizedError = normalizeTuttidError(error);
  const code = normalizedError?.code ?? getTuttidProtocolErrorCode(error);
  const reason = normalizedError?.reason ?? null;
  return (
    code === "workspace_terminal_not_found" ||
    (code === "invalid_request" && reason === "workspace_terminal_not_running")
  );
}

function toTerminalSessionDescriptor(
  session: Awaited<ReturnType<TuttidClient["createWorkspaceTerminal"]>>
): TerminalSessionDescriptor {
  return {
    cwd: session.cwd,
    profileId: session.profileId,
    runtimeKind: session.runtimeKind,
    sessionId: session.id,
    status: session.status,
    title: session.title
  };
}

function waitForWebSocketOpen(socket: WebSocket): Promise<void> {
  if (socket.readyState === WebSocket.OPEN) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    socket.addEventListener("open", () => resolve(), { once: true });
    socket.addEventListener(
      "error",
      () => reject(new Error("Terminal WebSocket connection failed.")),
      { once: true }
    );
  });
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function encodeBinaryWebSocketPayload(data: string): string {
  const bytes = Uint8Array.from(data, (value) => value.charCodeAt(0) & 0xff);
  let binary = "";
  for (const value of bytes) {
    binary += String.fromCharCode(value);
  }
  return globalThis.btoa(binary);
}

interface TerminalWebSocketFrame {
  code?: number | null;
  cwd?: string | null;
  data?: string;
  error?: string | null;
  fromSeq?: number | null;
  profileId?: string | null;
  runtimeKind?: TerminalMetadataEvent["runtimeKind"];
  seq?: number;
  sessionId: string;
  signal?: string | null;
  status?: TerminalStateEvent["status"];
  title?: string | null;
  toSeq?: number | null;
  type: "error" | "exit" | "gap" | "metadata" | "output" | "state";
}

function parseTerminalWebSocketFrame(
  data: unknown
): TerminalWebSocketFrame | null {
  if (typeof data !== "string") {
    return null;
  }
  try {
    const parsed = JSON.parse(data) as Partial<TerminalWebSocketFrame>;
    return typeof parsed.type === "string" &&
      typeof parsed.sessionId === "string"
      ? (parsed as TerminalWebSocketFrame)
      : null;
  } catch {
    return null;
  }
}
