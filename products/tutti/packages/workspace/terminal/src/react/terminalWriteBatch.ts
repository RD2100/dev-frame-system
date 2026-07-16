export interface TerminalWriteBatch {
  nextWrite: string;
  remainingChunks: string[];
}

export function drainTerminalWriteBatch(
  chunks: string[],
  maxBytes: number
): TerminalWriteBatch {
  let remaining = maxBytes;
  let nextWrite = "";
  const remainingChunks = chunks.slice();

  while (remaining > 0 && remainingChunks.length > 0) {
    const chunk = remainingChunks.shift() ?? "";
    if (chunk.length <= remaining) {
      nextWrite += chunk;
      remaining -= chunk.length;
      continue;
    }
    nextWrite += chunk.slice(0, remaining);
    remainingChunks.unshift(chunk.slice(remaining));
    remaining = 0;
  }

  return {
    nextWrite,
    remainingChunks
  };
}
