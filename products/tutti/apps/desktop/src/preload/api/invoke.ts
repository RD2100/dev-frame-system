import type {
  DesktopInvokeChannel,
  DesktopInvokePayloadByChannel,
  DesktopInvokeResultByChannel,
  DesktopIpcResult
} from "../../shared/contracts/ipc";
import { ipcRenderer } from "electron";
import { DesktopApiError } from "./desktopApiError";

export function invokeDesktopApi<TChannel extends DesktopInvokeChannel>(
  channel: TChannel,
  ...args: DesktopInvokePayloadByChannel[TChannel] extends undefined
    ? []
    : [payload: DesktopInvokePayloadByChannel[TChannel]]
): Promise<DesktopInvokeResultByChannel[TChannel]> {
  const payload = args[0];

  return ipcRenderer.invoke(channel, payload).then((result) => {
    const typedResult = result as DesktopIpcResult<
      DesktopInvokeResultByChannel[TChannel]
    >;
    if (typedResult.ok) {
      return typedResult.data;
    }

    throw new DesktopApiError(typedResult.error);
  });
}
