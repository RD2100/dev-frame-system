import {
  createTuttidClient,
  type TuttidClient
} from "@tutti-os/client-tuttid-ts";
import {
  createTuttidManager,
  type TuttidManager
} from "./daemon/tuttidManager";
import { createDesktopDaemonFetch } from "./transport/fetch";
import {
  resolveDesktopDaemonEndpoint,
  type DesktopDaemonEndpoint
} from "./transport/paths";

export interface DesktopDaemonRuntime {
  daemonEndpoint: DesktopDaemonEndpoint;
  tuttid: TuttidManager;
  tuttidClient: TuttidClient;
}

export function createDesktopDaemonRuntime(): DesktopDaemonRuntime {
  const daemonEndpoint = resolveDesktopDaemonEndpoint();
  const tuttidClient = createTuttidClient({
    auth: daemonEndpoint.accessToken,
    fetch: createDesktopDaemonFetch(() => daemonEndpoint)
  });
  const tuttid = createTuttidManager(daemonEndpoint, tuttidClient);

  return {
    daemonEndpoint,
    tuttid,
    tuttidClient
  };
}
