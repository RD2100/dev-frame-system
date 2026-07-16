import type { ILink, ILinkProvider, Terminal } from "@xterm/xterm";
import type { TerminalNodeFeature } from "../core/feature.ts";
import {
  detectTerminalFileLinks,
  toTerminalLinkTarget
} from "../core/index.ts";

export function createTerminalFileLinkProvider(input: {
  feature: TerminalNodeFeature;
  getCwd: () => string | null;
  terminal: Terminal;
}): ILinkProvider {
  return {
    provideLinks(bufferLineNumber, callback) {
      if (!input.feature.linkHandler) {
        callback(undefined);
        return;
      }

      const line = input.terminal.buffer.active.getLine(bufferLineNumber - 1);
      if (!line) {
        callback(undefined);
        return;
      }

      const text = line.translateToString(true);
      const links = detectTerminalFileLinks(text).map<ILink>((link) => ({
        activate: () => {
          void input.feature.linkHandler?.open({
            ...toTerminalLinkTarget(link),
            cwd: input.getCwd()
          });
        },
        range: {
          end: {
            x: link.index + link.text.length,
            y: bufferLineNumber
          },
          start: {
            x: link.index + 1,
            y: bufferLineNumber
          }
        },
        text: link.text
      }));

      callback(links.length > 0 ? links : undefined);
    }
  };
}
