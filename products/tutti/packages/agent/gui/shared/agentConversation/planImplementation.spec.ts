import { describe, expect, it } from "vitest";
import {
  PLAN_IMPLEMENTATION_ACTION_IMPLEMENT,
  PLAN_IMPLEMENTATION_PROMPT,
  latestPlanTurnId,
  planDecisionOps
} from "./planImplementation";

describe("latestPlanTurnId", () => {
  it("returns the turn id when the latest turn produced a plan item", () => {
    expect(
      latestPlanTurnId([
        { turnId: "turn-1", occurredAtUnixMs: 1, payload: {} },
        {
          turnId: "turn-1",
          occurredAtUnixMs: 2,
          payload: { messageKind: "plan" }
        }
      ])
    ).toBe("turn-1");
  });

  it("returns null when the latest turn has no plan item", () => {
    expect(
      latestPlanTurnId([
        {
          turnId: "turn-1",
          occurredAtUnixMs: 1,
          payload: { messageKind: "plan" }
        },
        { turnId: "turn-2", occurredAtUnixMs: 2, payload: {} }
      ])
    ).toBeNull();
  });

  it("ignores plan items that are not in the latest turn", () => {
    expect(
      latestPlanTurnId([
        {
          turnId: "turn-1",
          occurredAtUnixMs: 5,
          payload: { messageKind: "plan" }
        },
        { turnId: "turn-2", occurredAtUnixMs: 9, payload: {} }
      ])
    ).toBeNull();
  });

  it("returns null without any timeline items", () => {
    expect(latestPlanTurnId([])).toBeNull();
  });

  it("submits the same literal message as the codex TUI", () => {
    expect(PLAN_IMPLEMENTATION_PROMPT).toBe("Implement the plan.");
  });
});

describe("planDecisionOps", () => {
  it("turns a codex implement decision into planMode-off then literal sendInput", () => {
    expect(
      planDecisionOps({
        promptKind: "plan-implementation",
        action: PLAN_IMPLEMENTATION_ACTION_IMPLEMENT,
        requestId: "turn-1"
      })
    ).toEqual([
      { type: "updateSettings", settings: { planMode: false } },
      { type: "sendInput", text: PLAN_IMPLEMENTATION_PROMPT }
    ]);
  });

  it("no-ops a plan-implementation decision that is not implement", () => {
    expect(
      planDecisionOps({
        promptKind: "plan-implementation",
        action: "skip",
        requestId: "turn-1"
      })
    ).toEqual([]);
  });

  it("routes exit-plan and approval through submitInteractive", () => {
    expect(
      planDecisionOps({
        promptKind: "exit-plan",
        action: "allow",
        optionId: "acceptEdits",
        requestId: "req-1"
      })
    ).toEqual([
      {
        type: "submitInteractive",
        requestId: "req-1",
        action: "allow",
        optionId: "acceptEdits"
      }
    ]);
  });

  it("omits optional submitInteractive fields when not provided", () => {
    expect(
      planDecisionOps({ promptKind: "approval", requestId: "req-2" })
    ).toEqual([{ type: "submitInteractive", requestId: "req-2" }]);
  });
});
