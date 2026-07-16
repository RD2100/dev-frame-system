import { mkdir, readFile, rm, appendFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { TuttidClient, TrackEvent } from "@tutti-os/client-tuttid-ts";
import { resolveDesktopDefaultsFromEnv } from "./defaults.ts";
import {
  classifyDesktopErrorCode,
  type DesktopErrorCode
} from "../shared/errors/desktopErrors.ts";

export type StartupFailureEventName =
  | "app.startup_failed"
  | "daemon.startup_failed";

export interface StartupFailureEventInput {
  error: unknown;
  name: StartupFailureEventName;
  now?: () => number;
  process?: "main" | "renderer";
  queuePath?: string;
}

export interface FlushStartupFailureEventsInput {
  tuttidClient: Pick<TuttidClient, "trackEvents">;
  queuePath?: string;
}

export async function recordStartupFailureEvent(
  input: StartupFailureEventInput
): Promise<void> {
  const event = createStartupFailureEvent(input);
  const queuePath = input.queuePath ?? resolveStartupFailureQueuePath();
  await mkdir(dirname(queuePath), { recursive: true });
  await appendFile(queuePath, `${JSON.stringify(event)}\n`, "utf8");
}

export async function flushStartupFailureEvents(
  input: FlushStartupFailureEventsInput
): Promise<void> {
  const queuePath = input.queuePath ?? resolveStartupFailureQueuePath();
  let content: string;
  try {
    content = await readFile(queuePath, "utf8");
  } catch {
    return;
  }

  const events = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map(parseQueuedStartupFailureEvent)
    .filter((event): event is TrackEvent => event !== null);

  if (events.length === 0) {
    await rm(queuePath, { force: true });
    return;
  }

  await input.tuttidClient.trackEvents(events);
  await rm(queuePath, { force: true });
}

export function createStartupFailureEvent(
  input: StartupFailureEventInput
): TrackEvent {
  const errorType = classifyDesktopErrorCode(input.error);
  const params =
    input.name === "app.startup_failed"
      ? {
          error_message: resolveSafeStartupErrorMessage(errorType),
          error_type: errorType,
          process: input.process ?? "main"
        }
      : {
          error_message: resolveSafeStartupErrorMessage(errorType),
          error_type: errorType
        };

  return {
    client_ts: input.now?.() ?? Date.now(),
    name: input.name,
    params
  };
}

function parseQueuedStartupFailureEvent(line: string): TrackEvent | null {
  try {
    const value = JSON.parse(line) as Partial<TrackEvent>;
    if (
      typeof value.name !== "string" ||
      typeof value.client_ts !== "number" ||
      !value.params ||
      typeof value.params !== "object"
    ) {
      return null;
    }
    if (
      value.name !== "app.startup_failed" &&
      value.name !== "daemon.startup_failed"
    ) {
      return null;
    }
    return {
      client_ts: value.client_ts,
      name: value.name,
      params: { ...value.params }
    };
  } catch {
    return null;
  }
}

function resolveStartupFailureQueuePath(): string {
  return join(
    resolveDesktopDefaultsFromEnv().state.rootDir,
    "analytics",
    "startup-failures.jsonl"
  );
}

function resolveSafeStartupErrorMessage(errorType: DesktopErrorCode): string {
  switch (errorType) {
    case "daemon_unavailable":
      return "Daemon runtime information is unavailable.";
    case "node_runtime_broken":
      return "Node runtime failed to start.";
    case "transport_connect_failed":
      return "Daemon connection failed.";
    case "transport_timeout":
      return "Startup dependency did not become ready before timeout.";
    default:
      return "Desktop startup failed.";
  }
}
