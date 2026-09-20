/** Shadow sidebar entry dictionaries: the resident foot card's trigger row and its manage dropdown. */

export const NS = 'shadow'

/** Simplified Chinese Shadow entry messages. */
export const zh = {
  'trigger.label': '影子',
  'trigger.aria': '打开影子对话',
  'trigger.manage': '管理',
  'panel.rootsEmpty': '未授权任何根目录。',
  'manage.group.status': '状态',
  'manage.status.label': 'Shadow 状态',
  'manage.session.label': '控制者会话',
  'manage.group.roots': '授权根目录',
  'manage.group.controller': '控制器',
  'manage.controller.profile': '控制器预设',
  'manage.controller.value': '标准',
  'status.loading': '读取状态中…',
  'status.error': '状态读取失败',
  'status.disabled': 'Shadow 未启用',
  'status.configured': '已配置，未在线',
  'status.online': '在线',
  'status.issue': '影子会话缺少工作区',
  'detail.unmounted': '此部署没有挂载 Shadow 服务。',
  'detail.issue': '影子会话缺少工作区，请在部署配置中设置 designatedCwd 后重启。',
  'detail.configured': '控制者会话尚未标记为 Shadow。',
} satisfies Record<string, string>

/** Translation keys owned by the Shadow entry namespace. */
export type ShadowKey = keyof typeof zh

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Shadow sidebar entry copy. */
    shadow: ShadowKey
  }
}

/** English Shadow entry messages. */
export const en: Record<ShadowKey, string> = {
  'trigger.label': 'Shadow',
  'trigger.aria': 'Open the Shadow conversation',
  'trigger.manage': 'Manage',
  'panel.rootsEmpty': 'No root is authorized.',
  'manage.group.status': 'Status',
  'manage.status.label': 'Shadow status',
  'manage.session.label': 'Controller session',
  'manage.group.roots': 'Authorized roots',
  'manage.group.controller': 'Controller',
  'manage.controller.profile': 'Controller preset',
  'manage.controller.value': 'standard',
  'status.loading': 'Reading status…',
  'status.error': 'Status read failed',
  'status.disabled': 'Shadow is not enabled',
  'status.configured': 'Configured, not live',
  'status.online': 'Online',
  'status.issue': 'Shadow session lacks a workspace',
  'detail.unmounted': 'This deployment mounts no Shadow router.',
  'detail.issue': 'The Shadow session lacks a workspace; set designatedCwd in the deployment config and restart.',
  'detail.configured': 'The controller session is not marked as the Shadow yet.',
}
