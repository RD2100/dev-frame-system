export const workspaceAppIdPattern = /^[a-z0-9]+(?:[._-][a-z0-9]+)*$/;

export function isWorkspaceAppId(value: string): boolean {
  return workspaceAppIdPattern.test(value);
}

export function normalizeWorkspaceAppId(value: string): string {
  return value.trim().toLowerCase();
}

export function createWorkspaceAppIdentity(input: {
  readonly id: string;
}): string {
  return normalizeWorkspaceAppId(input.id);
}
