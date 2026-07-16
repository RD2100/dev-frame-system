import { describe, expect, it } from "vitest";

import { pendingInterruptActionForDisplayStatus } from "./pendingInterrupt";

describe("pendingInterruptActionForDisplayStatus", () => {
  it("fires the deferred cancel once the turn is live", () => {
    expect(pendingInterruptActionForDisplayStatus("working")).toBe("fire");
  });

  it("clears the deferred cancel when the session settled without a live turn", () => {
    // Regression: a cancel that raced startup must not interrupt a later,
    // unrelated turn. Once the startup turn settles, drop the deferred intent.
    expect(pendingInterruptActionForDisplayStatus("completed")).toBe("clear");
    expect(pendingInterruptActionForDisplayStatus("failed")).toBe("clear");
    expect(pendingInterruptActionForDisplayStatus("canceled")).toBe("clear");
  });

  it("keeps waiting while the session is still connecting or paused", () => {
    expect(pendingInterruptActionForDisplayStatus(null)).toBe("wait");
    expect(pendingInterruptActionForDisplayStatus("waiting")).toBe("wait");
  });
});
