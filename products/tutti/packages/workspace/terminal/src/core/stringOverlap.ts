export function resolveSuffixPrefixOverlap(
  left: string,
  right: string
): number {
  if (left.length === 0 || right.length === 0) {
    return 0;
  }

  const max = Math.min(left.length, right.length);
  const leftTail = left.slice(-max);
  const rightPrefix = right.slice(0, max);
  const combined = `${rightPrefix}\u0000${leftTail}`;
  const prefix = new Uint32Array(combined.length);
  let cursor = 0;

  for (let index = 1; index < combined.length; index += 1) {
    while (cursor > 0 && combined[index] !== combined[cursor]) {
      cursor = prefix[cursor - 1] ?? 0;
    }

    if (combined[index] === combined[cursor]) {
      cursor += 1;
      prefix[index] = cursor;
    }
  }

  return prefix[combined.length - 1] ?? 0;
}
