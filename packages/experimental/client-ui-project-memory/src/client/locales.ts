/** Library page dictionaries. */

/** Locale namespace owned by the Library page. */
export const NS = 'library'

/** Simplified Chinese Library messages. */
export const zh = {
  'center.title': '记忆库管理',
  refresh: '刷新记忆库',
  loading: '正在读取记忆库…',
  'status.error': '读取失败',
  'status.unavailable': '记忆库未配置',
  'status.unavailableReason': '当前部署未配置 Vault 目录，记忆库不可用。',
  fileCount: '{count} 个文件',
  'search.label': '搜索记忆库',
  'search.placeholder': '搜索文件名或内容',
  'search.action': '搜索',
  'search.clear': '清除搜索',
  'search.empty': '没有匹配的文件。',
  'empty.title': '还没有记忆笔记',
  'empty.hint': '与助手对话产生的重要事实会自动记录在这里。',
  'card.untitled': '无标题',
  'card.kind.fact': '事实',
  'card.kind.preference': '偏好',
  'card.reference': '引用',
  'filter.all': '全部',
  'filter.fact': '事实',
  'filter.preference': '偏好',
  'preview.title': '笔记详情',
  'preview.close': '关闭预览',
  'preview.path': '路径',
  'copyPath': '复制路径',
  'copyPath.copied': '已复制',
  'copyPath.failed': '复制失败',
  'reference': '引用到对话',
  'reference.inserted': '已引用',
  'reference.noSession': '没有可引用的会话',
  'reference.failed': '读取文件失败，无法引用。',
} satisfies Record<string, string>

/** Translation keys owned by the library namespace. */
export type LibraryKey = keyof typeof zh

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Library page copy. */
    'library': LibraryKey
  }
}

/** English Library messages, checked against the Chinese key set. */
export const en: Record<LibraryKey, string> = {
  'center.title': 'Library manager',
  refresh: 'Refresh library',
  loading: 'Reading the library…',
  'status.error': 'Read failed',
  'status.unavailable': 'Library is not configured',
  'status.unavailableReason': 'This deployment has no Vault directory, so the library is unavailable.',
  fileCount: '{count} files',
  'search.label': 'Search the library',
  'search.placeholder': 'Search file names or content',
  'search.action': 'Search',
  'search.clear': 'Clear search',
  'search.empty': 'No files match this search.',
  'empty.title': 'No memory notes yet',
  'empty.hint': 'Facts and preferences mentioned in conversations will be recorded here',
  'card.untitled': 'Untitled',
  'card.kind.fact': 'Fact',
  'card.kind.preference': 'Preference',
  'card.reference': 'Reference',
  'filter.all': 'All',
  'filter.fact': 'Facts',
  'filter.preference': 'Preferences',
  'preview.title': 'Note detail',
  'preview.close': 'Close preview',
  'preview.path': 'Path',
  'copyPath': 'Copy path',
  'copyPath.copied': 'Copied',
  'copyPath.failed': 'Copy failed',
  'reference': 'Reference in conversation',
  'reference.inserted': 'Referenced',
  'reference.noSession': 'No conversation to reference',
  'reference.failed': 'The file could not be read and was not referenced.',
}
