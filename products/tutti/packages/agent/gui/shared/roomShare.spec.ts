import { describe, expect, it } from "vitest";
import { buildRoomShareText, parseRoomShareJoinInput } from "./roomShare";

describe("room share text i18n", () => {
  it("builds English invite text by default and parses it back", () => {
    const text = buildRoomShareText({
      roomId: "room-1",
      inviteCode: "abc123"
    });

    expect(text).toContain("\nInvite code: abc123");
    expect(parseRoomShareJoinInput(text)).toMatchObject({
      inviteCode: "abc123",
      roomId: "room-1"
    });
  });

  it("builds Chinese invite text when requested and keeps legacy parsing", () => {
    const text = buildRoomShareText(
      {
        roomId: "room-1",
        inviteCode: "abc123"
      },
      { locale: "zh-CN" }
    );

    expect(text).toContain("\n邀请码: abc123");
    expect(parseRoomShareJoinInput(text)).toMatchObject({
      inviteCode: "abc123",
      roomId: "room-1"
    });
    expect(
      parseRoomShareJoinInput(
        "https://tutti.sh/tutti-share/room-1\n邀请码：legacy"
      )
    ).toMatchObject({
      inviteCode: "legacy",
      roomId: "room-1"
    });
  });

  it("parses common English invite labels", () => {
    expect(
      parseRoomShareJoinInput(
        "https://tutti.sh/tutti-share/room-1\ninvite: short"
      )
    ).toMatchObject({
      inviteCode: "short",
      roomId: "room-1"
    });
  });
});
