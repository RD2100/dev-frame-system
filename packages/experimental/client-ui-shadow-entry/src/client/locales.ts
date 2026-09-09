/** Shadow sidebar entry dictionaries: the resident foot card and its status panel. */

export const NS = 'shadow'

/** Simplified Chinese Shadow entry messages. */
export const zh = {
  'trigger.label': '影子',
  'trigger.aria': 'Shadow 服务状态',
  'panel.aria': 'Shadow 服务状态面板',
  'panel.title': 'Shadow 状态',
  'panel.session': '控制者会话',
  'panel.roots': '授权根目录',
  'panel.rootsEmpty': '未授权任何根目录。',
  'panel.bindings': '项目绑定',
  'panel.bindingsEmpty': '暂无项目绑定。',
  'binding.revision': '修订 {revision}',
  'status.loading': '读取状态中…',
  'status.error': '状态读取失败',
  'status.disabled': 'Shadow 未启用',
  'status.configured': '已配置，未在线',
  'status.online': '在线',
  'detail.unmounted': '此部署没有挂载 Shadow 服务。',
  'detail.disabled': '宿主组合尚未声明控制者会话。',
  'detail.configured': '控制者会话尚未标记为 Shadow。',
  'status.readFailed': '读取 Shadow 状态失败：{message}',
  'state.reserving': '预留中',
  'state.provisioning': '开通中',
  'state.ready': '就绪',
  'state.stopping': '停止中',
  'state.stopped': '已停止',
  'state.needsAttention': '需要关注',
  'state.failed': '失败',
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
  'trigger.aria': 'Shadow service status',
  'panel.aria': 'Shadow service status panel',
  'panel.title': 'Shadow status',
  'panel.session': 'Controller session',
  'panel.roots': 'Authorized roots',
  'panel.rootsEmpty': 'No root is authorized.',
  'panel.bindings': 'Project bindings',
  'panel.bindingsEmpty': 'No project bindings.',
  'binding.revision': 'Revision {revision}',
  'status.loading': 'Reading status…',
  'status.error': 'Status read failed',
  'status.disabled': 'Shadow is not enabled',
  'status.configured': 'Configured, not live',
  'status.online': 'Online',
  'detail.unmounted': 'This deployment mounts no Shadow router.',
  'detail.disabled': 'The host composition declares no controller session.',
  'detail.configured': 'The controller session is not marked as the Shadow yet.',
  'status.readFailed': 'Reading the Shadow status failed: {message}',
  'state.reserving': 'Reserving',
  'state.provisioning': 'Provisioning',
  'state.ready': 'Ready',
  'state.stopping': 'Stopping',
  'state.stopped': 'Stopped',
  'state.needsAttention': 'Needs attention',
  'state.failed': 'Failed',
}
