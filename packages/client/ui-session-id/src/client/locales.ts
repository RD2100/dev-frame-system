/** `session-id` namespace dictionaries. */

/** Dictionary namespace owned by this plugin. */
export const NS = 'session-id'

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'badge.aria': '会话 ID',
  'copy': '复制会话 ID',
  'copied': '已复制',
} as const

/** English dictionary, key-identical to the Chinese source of truth. */
export const en: Record<SessionIdKey, string> = {
  'badge.aria': 'Session ID',
  'copy': 'Copy session ID',
  'copied': 'Copied',
}

/** Key domain of the `session-id` namespace (zh is the source of truth). */
export type SessionIdKey = keyof typeof zh
