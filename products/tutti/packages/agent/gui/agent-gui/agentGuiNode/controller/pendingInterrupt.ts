/**
 * Decide what to do with a deferred cancel — one that was armed when a user
 * cancel raced session startup — given the session's current activity display
 * status.
 *
 * - `"fire"`: the startup turn is live now, so issue the interrupt.
 * - `"clear"`: the turn settled without being interrupted, so drop the deferred
 *   intent; it must not interrupt a later, unrelated turn in the same session.
 * - `"wait"`: still connecting or paused — keep the deferred cancel armed.
 */
export function pendingInterruptActionForDisplayStatus(
  status: string | null
): "fire" | "clear" | "wait" {
  if (status === "working") {
    return "fire";
  }
  if (status === "completed" || status === "failed" || status === "canceled") {
    return "clear";
  }
  return "wait";
}
