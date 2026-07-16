import type {
  AgentHostGenerateRoomShareInput,
  AgentHostMockSession,
  AgentHostUserInfo,
  AgentHostRoomShareResult,
  AgentHostRoomShareInviteSlot,
  AgentHostRoomShareMember,
  AgentHostRoomShareState,
  AgentHostRoomSummary
} from "./contracts/dto";

export const TUTTI_SHARE_PRODUCTION_ORIGIN = "https://tutti.sh";

export interface ParsedRoomShareJoinInput {
  roomId: string;
  inviteCode: string | null;
  roomName: string | null;
  issueId: string | null;
}

export type RoomShareTextLocale = "en" | "zh-CN";

export interface BuildRoomShareTextOptions {
  inviteCodeLabel?: string;
  locale?: RoomShareTextLocale;
}

export interface ExplicitRoomShareInviteClient {
  createShareInvite(
    input: AgentHostGenerateRoomShareInput
  ): Promise<AgentHostRoomShareResult>;
  generateShare(
    input: AgentHostGenerateRoomShareInput
  ): Promise<AgentHostRoomShareResult>;
}

function normalizePastedUrlCandidate(input: string): string {
  let next = input.trim();
  while (/^[<([{'"“‘「『]+/.test(next)) {
    next = next.slice(1).trimStart();
  }
  while (/[>)\]}"'”’」』，。！？!?;；,:]+$/.test(next)) {
    next = next.slice(0, -1).trimEnd();
  }
  return next;
}

export function requestExplicitRoomShareInvite(
  roomClient: ExplicitRoomShareInviteClient,
  input: AgentHostGenerateRoomShareInput
): Promise<AgentHostRoomShareResult> {
  return roomClient.createShareInvite(input);
}

/**
 * Parses a pasted room share link (https …/tutti-share/…, legacy …/tutti/share/…, or tutti:// …/join…),
 * optional multiline invite-code line, or a bare room UUID in text.
 */
export function parseRoomShareJoinInput(
  raw: string
): ParsedRoomShareJoinInput | null {
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }

  const firstUrlMatch = trimmed.match(/https?:\/\/[^\s]+/i);
  const candidate = normalizePastedUrlCandidate(
    firstUrlMatch
      ? firstUrlMatch[0]
      : (trimmed.split("\n")[0]?.trim() ?? trimmed)
  );

  const inviteFromText = (text: string): string | null => {
    const m = text.match(/(?:邀请码|invite(?:\s+code)?)[：:]\s*(\S+)/iu);
    return m?.[1]?.trim() || null;
  };
  const fallbackInvite = inviteFromText(trimmed);

  try {
    const url = new URL(candidate);
    const sharePath = url.pathname.replace(/\/+$/, "");
    const shareMatch = sharePath.match(
      /^\/(?:tutti\/share|tutti-share)\/(.+)$/
    );
    if (shareMatch) {
      const roomId = decodeURIComponent(shareMatch[1] ?? "");
      const fromQuery = url.searchParams.get("inviteCode")?.trim() || null;
      const roomName = url.searchParams.get("name")?.trim() || null;
      const issueId = url.searchParams.get("issueId")?.trim() || null;
      if (roomId) {
        return {
          roomId,
          inviteCode: fromQuery || fallbackInvite,
          roomName,
          issueId
        };
      }
    }
    if (
      isSupportedRoomShareProtocol(url.protocol) &&
      (url.hostname === "room" || url.hostname === "workspace")
    ) {
      const pathname = url.pathname.replace(/\/+$/, "");
      if (pathname === "/join") {
        const roomId =
          url.searchParams.get("roomId")?.trim() ||
          url.searchParams.get("workspaceId")?.trim() ||
          "";
        const inviteCode =
          url.searchParams.get("inviteCode")?.trim() ||
          url.searchParams.get("code")?.trim() ||
          null;
        if (roomId) {
          return {
            roomId,
            inviteCode: inviteCode || fallbackInvite,
            roomName: null,
            issueId: url.searchParams.get("issueId")?.trim() || null
          };
        }
      }
    }
    if (
      isSupportedRoomShareProtocol(url.protocol) &&
      url.hostname === "invite"
    ) {
      const roomId = decodeURIComponent(
        url.pathname.replace(/^\/+|\/+$/g, "")
      ).trim();
      const inviteCode =
        url.searchParams.get("inviteCode")?.trim() ||
        url.searchParams.get("code")?.trim() ||
        null;
      if (roomId) {
        return {
          roomId,
          inviteCode: inviteCode || fallbackInvite,
          roomName: null,
          issueId: url.searchParams.get("issueId")?.trim() || null
        };
      }
    }
  } catch {
    // fall through
  }

  const uuidMatch = trimmed.match(
    /\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/i
  );
  if (uuidMatch) {
    return {
      roomId: uuidMatch[1] ?? "",
      inviteCode: fallbackInvite,
      roomName: null,
      issueId: null
    };
  }

  return null;
}

function isSupportedRoomShareProtocol(protocol: string): boolean {
  return protocol === "tutti:";
}

export interface RoomShareMemberView {
  userId: string;
  label: string;
  role: "owner" | "member";
  initial: string;
  /** Resolved avatar URL; falls back to `initial` in UI when missing or load fails. */
  avatarUrl?: string;
}

export type BuildRoomShareMembersOptions = {
  session?: Pick<AgentHostMockSession, "userId" | "avatar"> | null;
  userProfilesById?: Record<
    string,
    Pick<AgentHostUserInfo, "userId" | "email" | "avatar" | "name">
  >;
};

export interface NormalizedRoomVisitorShareViewState {
  enabled: boolean;
  allowRoomContext: boolean;
  webLink: string | null;
}

function trimUrl(input: string | null | undefined): string | undefined {
  const next = input?.trim();
  return next || undefined;
}

function readMemberAvatarField(
  member: AgentHostRoomShareMember
): string | undefined {
  const anyMember = member as AgentHostRoomShareMember & {
    avatar_url?: string;
  };
  return trimUrl(anyMember.avatarUrl ?? anyMember.avatar_url);
}

function resolveRoomShareMemberAvatar(
  userId: string,
  member: AgentHostRoomShareMember | null,
  options: BuildRoomShareMembersOptions | undefined
): string | undefined {
  const id = userId.trim();
  const profileAvatar = trimUrl(options?.userProfilesById?.[id]?.avatar);
  if (profileAvatar) {
    return profileAvatar;
  }
  if (member) {
    const fromApi = readMemberAvatarField(member);
    if (fromApi) {
      return fromApi;
    }
  }
  const sessionUserId = options?.session?.userId?.trim();
  if (sessionUserId && sessionUserId === id) {
    return trimUrl(options?.session?.avatar);
  }
  return undefined;
}

export function buildRoomShareWebLink(
  roomId: string,
  inviteCode?: string | null,
  roomName?: string | null,
  issueId?: string | null
): string {
  const url = new URL(
    `/tutti-share/${encodeURIComponent(roomId)}`,
    TUTTI_SHARE_PRODUCTION_ORIGIN
  );
  const normalizedInviteCode = inviteCode?.trim();
  if (normalizedInviteCode) {
    url.searchParams.set("inviteCode", normalizedInviteCode);
  }
  const normalizedName = roomName?.trim();
  if (normalizedName) {
    url.searchParams.set("name", normalizedName);
  }
  const normalizedIssueId = issueId?.trim();
  if (normalizedIssueId) {
    url.searchParams.set("issueId", normalizedIssueId);
  }
  return url.toString();
}

export function buildRoomVisitorShareWebLink(
  roomId: string,
  shareToken: string,
  roomName?: string | null
): string {
  const url = new URL(
    `/room/${encodeURIComponent(roomId)}`,
    TUTTI_SHARE_PRODUCTION_ORIGIN
  );
  url.searchParams.set("shareToken", shareToken.trim());
  const normalizedName = roomName?.trim();
  if (normalizedName) {
    url.searchParams.set("name", normalizedName);
  }
  return url.toString();
}

export function normalizeRoomVisitorShareFromState(
  state: AgentHostRoomShareState | null | undefined,
  roomName?: string | null
): NormalizedRoomVisitorShareViewState {
  const link = state?.visitorShareLink;
  const linkState = link?.state;
  if (!link || !linkState) {
    return {
      enabled: false,
      allowRoomContext: false,
      webLink: null
    };
  }

  const roomId = linkState.roomId?.trim() || state?.roomId?.trim() || "";
  const shareToken = link.shareToken?.trim();
  return {
    enabled: Boolean(linkState.enabled),
    allowRoomContext: Boolean(
      linkState.shareDirectoryTree || linkState.shareHistory
    ),
    webLink:
      linkState.enabled && roomId && shareToken
        ? buildRoomVisitorShareWebLink(roomId, shareToken, roomName)
        : null
  };
}

export function buildRoomShareText(
  input: {
    roomId: string;
    roomName?: string | null;
    inviteCode?: string | null;
    issueId?: string | null;
  },
  options: BuildRoomShareTextOptions = {}
): string {
  const link = buildRoomShareWebLink(
    input.roomId,
    input.inviteCode,
    input.roomName,
    input.issueId
  );
  const normalizedInviteCode = input.inviteCode?.trim();
  const label =
    options.inviteCodeLabel?.trim() ||
    (options.locale === "zh-CN" ? "邀请码" : "Invite code");
  return normalizedInviteCode
    ? `${link}\n${label}: ${normalizedInviteCode}`
    : link;
}

export function resolveMemberInitial(userId: string): string {
  const normalized = userId.trim();
  if (!normalized) {
    return "?";
  }
  return normalized.slice(0, 1).toUpperCase();
}

export function buildRoomShareMembers(
  room: AgentHostRoomSummary | null | undefined,
  state?: AgentHostRoomShareState | null,
  options?: BuildRoomShareMembersOptions
): RoomShareMemberView[] {
  const stateMembers = state?.members;
  if (Array.isArray(stateMembers) && stateMembers.length > 0) {
    return stateMembers.map((member) => {
      const userId = member.userId?.trim() || "unknown";
      const label = formatRoomShareMemberLabel(
        member,
        options?.userProfilesById?.[userId]
      );
      return {
        userId,
        label,
        role: member.role === "owner" ? "owner" : "member",
        initial: resolveMemberInitial(label || member.userId || "?"),
        avatarUrl: resolveRoomShareMemberAvatar(userId, member, options)
      };
    });
  }
  if (!room) {
    return [];
  }
  const ownerUserId = (room.ownerUserId ?? "").trim();
  const extraMemberIds = Array.isArray(room.memberUserIds)
    ? room.memberUserIds.map((userId) => userId.trim()).filter(Boolean)
    : [];
  const orderedIds = [ownerUserId, ...extraMemberIds].filter(Boolean);
  const uniqueIds = [...new Set(orderedIds)];
  return uniqueIds.map((userId) => ({
    userId,
    label: options?.userProfilesById?.[userId]?.name?.trim() || userId,
    role: userId === ownerUserId ? "owner" : "member",
    initial: resolveMemberInitial(
      options?.userProfilesById?.[userId]?.name?.trim() || userId
    ),
    avatarUrl: resolveRoomShareMemberAvatar(userId, null, options)
  }));
}

export function getRoomShareMemberUserIds(
  room: AgentHostRoomSummary | null | undefined,
  state?: AgentHostRoomShareState | null
): string[] {
  const stateMembers = state?.members;
  if (Array.isArray(stateMembers) && stateMembers.length > 0) {
    return uniqueUserIds(stateMembers.map((member) => member.userId));
  }

  const ownerUserId = (room?.ownerUserId ?? "").trim();
  const memberUserIds = Array.isArray(room?.memberUserIds)
    ? room.memberUserIds.map((userId) => userId.trim()).filter(Boolean)
    : [];
  return uniqueUserIds([ownerUserId, ...memberUserIds]);
}

export function formatRoomShareMemberLabel(
  member: AgentHostRoomShareMember,
  profile?: Pick<AgentHostUserInfo, "email" | "name">
): string {
  const displayName = member.displayName?.trim() ?? "";
  const email = member.email?.trim() ?? "";
  const profileName = profile?.name?.trim() ?? "";
  const profileEmail = profile?.email?.trim() ?? "";
  const userId = (member.userId ?? "").trim();
  if (profileName && profileEmail) {
    return `${profileName} (${profileEmail})`;
  }
  if (profileName || profileEmail) {
    return profileName || profileEmail;
  }
  if (displayName && email) {
    return `${displayName} (${email})`;
  }
  return displayName || email || userId;
}

export function buildFallbackRoomShareState(
  room: AgentHostRoomSummary | null | undefined,
  share: AgentHostRoomShareResult
): AgentHostRoomShareState {
  const members = buildFallbackShareMembers(room, share.roomId);
  const collaboratorCount = members.filter(
    (member) => member.role !== "owner"
  ).length;
  const maxCollaborators = 4;
  const inviteCode = share.inviteCode?.trim() || "";
  const fallbackSlotIndex =
    Number.isInteger(share.slotIndex) &&
    share.slotIndex !== undefined &&
    share.slotIndex >= 0
      ? share.slotIndex
      : undefined;
  const createdSlot = inviteCode
    ? {
        inviteId: share.inviteId,
        roomId: share.roomId,
        slotIndex: fallbackSlotIndex,
        inviteCode,
        status: share.status ?? "pending",
        createdAtUnix: share.createdAtUnix || share.rotatedAtUnix || undefined
      }
    : null;
  const invites: AgentHostRoomShareInviteSlot[] =
    createdSlot && fallbackSlotIndex !== undefined
      ? Array.from(
          { length: 4 },
          (_, index): AgentHostRoomShareInviteSlot =>
            index === fallbackSlotIndex
              ? createdSlot
              : { status: "empty", slotIndex: index }
        )
      : createdSlot
        ? [createdSlot]
        : [];

  return {
    roomId: share.roomId,
    maxCollaborators,
    maxActiveInvites: 4,
    collaboratorCount,
    remainingCollaboratorSlots: Math.max(
      0,
      maxCollaborators - collaboratorCount
    ),
    activeInviteCount: invites.filter((invite) => invite.status === "pending")
      .length,
    remainingActiveInviteSlots: Math.max(0, 4 - invites.length),
    members,
    invites
  };
}

export function mergeRoomShareStateWithCreatedInvite(
  room: AgentHostRoomSummary | null | undefined,
  state: AgentHostRoomShareState | null,
  share: AgentHostRoomShareResult,
  options?: {
    preferredSlotIndex?: number;
  }
): AgentHostRoomShareState {
  const inviteCode = share.inviteCode?.trim() || "";
  if (!inviteCode) {
    return state ?? buildFallbackRoomShareState(room, share);
  }

  const base = state ?? buildFallbackRoomShareState(room, share);
  const inviteId = share.inviteId?.trim() || "";
  const slotIndex =
    Number.isInteger(share.slotIndex) &&
    share.slotIndex !== undefined &&
    share.slotIndex >= 0
      ? share.slotIndex
      : undefined;
  const createdSlot: AgentHostRoomShareInviteSlot = {
    inviteId: share.inviteId,
    roomId: share.roomId,
    slotIndex,
    inviteCode,
    status: share.status && share.status !== "empty" ? share.status : "pending",
    createdAtUnix: share.createdAtUnix || share.rotatedAtUnix || undefined
  };
  const existingIndex = base.invites.findIndex((slot) => {
    const slotInviteId = slot.inviteId?.trim() || "";
    return (
      (inviteId && slotInviteId === inviteId) ||
      readSlotInviteCode(slot) === inviteCode
    );
  });

  const invites = [...base.invites];
  if (existingIndex >= 0) {
    invites[existingIndex] = {
      ...invites[existingIndex],
      ...createdSlot,
      inviteId: createdSlot.inviteId ?? invites[existingIndex]?.inviteId,
      roomId: createdSlot.roomId ?? invites[existingIndex]?.roomId,
      slotIndex: createdSlot.slotIndex ?? invites[existingIndex]?.slotIndex
    };
  } else {
    const preferredSlotIndex = slotIndex ?? options?.preferredSlotIndex;
    if (
      Number.isInteger(preferredSlotIndex) &&
      preferredSlotIndex !== undefined &&
      preferredSlotIndex >= 0
    ) {
      while (invites.length < preferredSlotIndex) {
        invites.push({ status: "empty", slotIndex: invites.length });
      }

      const preferredSlot = invites[preferredSlotIndex];
      if (preferredSlot) {
        invites[preferredSlotIndex] = {
          ...preferredSlot,
          ...createdSlot,
          inviteId: createdSlot.inviteId ?? preferredSlot.inviteId,
          roomId: createdSlot.roomId ?? preferredSlot.roomId
        };
      } else {
        invites[preferredSlotIndex] = createdSlot;
      }
    } else {
      invites.unshift(createdSlot);
    }
  }

  const activeInviteCount = invites.filter(
    (invite) => invite.status === "pending"
  ).length;
  const maxActiveInvites = base.maxActiveInvites || 4;
  return {
    ...base,
    roomId: base.roomId || share.roomId,
    invites,
    activeInviteCount,
    remainingActiveInviteSlots: Math.max(
      0,
      maxActiveInvites - activeInviteCount
    )
  };
}

function readSlotInviteCode(slot: { inviteCode?: string | null }): string {
  return slot.inviteCode?.trim() || "";
}

function buildFallbackShareMembers(
  room: AgentHostRoomSummary | null | undefined,
  roomId: string
): AgentHostRoomShareMember[] {
  const ownerUserId = room?.ownerUserId?.trim() || "";
  const memberIds = (room?.memberUserIds ?? [])
    .map((userId) => userId.trim())
    .filter(Boolean);
  const uniqueIds = [...new Set([ownerUserId, ...memberIds].filter(Boolean))];
  if (uniqueIds.length === 0) {
    return [];
  }
  return uniqueIds.map((userId) => ({
    userId,
    role:
      userId === ownerUserId || (ownerUserId === "" && userId === roomId)
        ? "owner"
        : "collaborator"
  }));
}

function uniqueUserIds(userIds: Array<string | null | undefined>): string[] {
  return [
    ...new Set(
      userIds.map((userId) => userId?.trim()).filter(Boolean) as string[]
    )
  ];
}
