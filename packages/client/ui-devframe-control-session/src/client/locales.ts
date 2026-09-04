/** Chinese dictionary for the DevFrame controller identity node. */
export const zh = {
  'title': 'DevFrame 控制器',
  'role': '角色',
  'sessionId': 'Session ID',
  'scopeId': 'Profile / 工作区 ID',
  'schemaVersion': 'Schema 版本',
  'readiness': '身份状态',
  'readiness.identityRecorded': '身份已记录',
  'readiness.blocked': '已阻断',
  'global.open': '总控',
  'global.actions': '总控操作',
  'global.copySessionId': '复制 Session ID',
  'global.unavailable': '总控未就绪',
} as const

/** Locale key union. */
export type ControlSessionKey = keyof typeof zh

/** English dictionary, complete against the Chinese key set. */
export const en = {
  'title': 'DevFrame controller',
  'role': 'Role',
  'sessionId': 'Session ID',
  'scopeId': 'Profile / workspace ID',
  'schemaVersion': 'Schema version',
  'readiness': 'Identity status',
  'readiness.identityRecorded': 'Identity recorded',
  'readiness.blocked': 'Blocked',
  'global.open': 'Global Controller',
  'global.actions': 'Global Controller actions',
  'global.copySessionId': 'Copy Session ID',
  'global.unavailable': 'Global Controller unavailable',
} as const satisfies Record<ControlSessionKey, string>

/** Locale namespace owned by this package. */
export const NS = 'client-ui-devframe-control-session'
