import { describe, expect, it } from "vitest";
import {
  agentHostSnapshotFromAgentActivitySnapshot,
  projectCoreSessionStatus
} from "./agentActivitySnapshotProjection";

describe("projectCoreSessionStatus", () => {
  it("maps core idle states to ready", () => {
    expect(projectCoreSessionStatus("active")).toBe("ready");
    expect(projectCoreSessionStatus("created")).toBe("ready");
    expect(projectCoreSessionStatus("queued")).toBe("ready");
    expect(projectCoreSessionStatus("waiting")).toBe("ready");
  });

  it("maps running to working and passes terminal states through", () => {
    expect(projectCoreSessionStatus("running")).toBe("working");
    expect(projectCoreSessionStatus("completed")).toBe("completed");
    expect(projectCoreSessionStatus("failed")).toBe("failed");
    expect(projectCoreSessionStatus("ready")).toBe("ready");
  });
});

describe("agentHostSnapshotFromAgentActivitySnapshot", () => {
  it("projects active runtime phases into host session status", () => {
    const hostSnapshot = agentHostSnapshotFromAgentActivitySnapshot({
      composerOptionsByProvider: {},
      presences: [],
      sessionMessagesById: {},
      sessions: [
        session("session-working", {
          currentPhase: "working",
          status: "active"
        }),
        session("session-idle", {
          currentPhase: "idle",
          status: "active",
          turnLifecycle: {
            activeTurnId: null,
            outcome: "completed",
            phase: "settled"
          }
        })
      ],
      workspaceId: "workspace-1"
    });

    expect(hostSnapshot.sessions[0]).toMatchObject({
      agentSessionId: "session-working",
      effectiveStatus: "working",
      lifecycleStatus: "active",
      status: "working",
      turnPhase: "working"
    });
    expect(hostSnapshot.sessions[1]).toMatchObject({
      agentSessionId: "session-idle",
      effectiveStatus: "completed",
      lifecycleStatus: "ended",
      status: "completed",
      turnPhase: "idle"
    });
  });
});

function session(
  agentSessionId: string,
  overrides: Record<string, unknown> = {}
) {
  return {
    agentSessionId,
    createdAtUnixMs: 1,
    cwd: "/workspace",
    provider: "claude-code",
    status: "queued",
    title: "Session",
    updatedAtUnixMs: 2,
    workspaceId: "workspace-1",
    ...overrides
  };
}
