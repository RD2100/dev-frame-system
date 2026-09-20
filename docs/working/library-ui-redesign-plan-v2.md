# #7 记忆库弹窗 UI 升级计划（v2 — 解决审核反馈）

## 背景
- 用户反馈：记忆库弹窗太简陋（只有搜索框+空提示），要求参考专家模式卡片网格 + Obsidian 记忆管理理念
- 当前状态：按钮消失问题已修复（根因：devframe-profile dependencies 缺 client-ui-project-memory）
- 上一版计划审核结论：**不通过**，两个必改问题：
  1. 不能直接删 `devframe-memory` 排除行 = 安全隔离回归
  2. 卡片元数据无数据来源（DTO 缺 kind/entities/createdAt）

## 本次范围
1. **host 端**：扩展 `LibraryFile` DTO，解析 frontmatter 提取 kind/entities/createdAt/summary
2. **host 端**：按 workspace 作用域纳入 `devframe-memory/projects/<workspaceId>/` + `devframe-memory/user/`，不暴露其他工作区私有笔记
3. **client 端**：恢复完整 LibraryPane 为卡片网格（专家模式风格）
4. **client 端**：卡片显示标题/日期/类型/摘要/实体标签

---

## 一、host 端改动

### 1.1 DTO 扩展（`project-memory/src/library.ts`）

当前 `LibraryFile`:
```ts
{ relativePath: string, size: number, mtimeMs: number }
```

扩展为：
```ts
{
  relativePath: string,
  size: number,
  mtimeMs: number,
  kind?: 'fact' | 'preference' | 'other',
  createdAt?: string,       // ISO date from frontmatter
  entities?: readonly string[],
  summary?: string,          // first 120 chars of body (after frontmatter)
}
```

**解析逻辑**：
- 读取文件前 2KB，尝试解析 YAML frontmatter（`---` 开头）
- 提取 `kind`、`createdAt`、`entities`
- summary 从 frontmatter 结束后的正文第一段提取，截断 120 字符
- 解析失败不报错，字段留空（降级显示）

### 1.2 workspace 作用域纳入 devframe-memory（`project-memory/src/library.ts`）

**当前行为**：`isForbiddenName('devframe-memory')` 整个目录被排除。

**新行为**：
- 不再整体排除 `devframe-memory/`
- 只允许访问：
  - `devframe-memory/projects/<currentWorkspaceId>/` — 当前工作区的笔记
  - `devframe-memory/user/` — 用户级笔记（已配置 userScopeEnabled: true）
- 仍然拒绝：
  - `devframe-memory/projects/<otherWorkspaceId>/` — 其他工作区的私有笔记
  - `../` 路径穿越（已有逻辑不变）

**实现方式**：
- `listLibraryFiles` 需要知道当前 workspaceId
- 从 gateway 配置或 service context 获取
- 过滤逻辑：如果 relativePath 以 `devframe-memory/projects/` 开头，检查第二段是否等于当前 workspaceId

### 1.3 gateway 改动（`project-memory/src/gateway.ts`）
- `view()` 和 `list()` 返回扩展后的 DTO
- `search()` 结果也携带元数据

---

## 二、client 端改动

### 2.1 恢复 LibraryPane 为卡片网格

**布局**：
- 顶部：标题 + 刷新按钮 + 关闭按钮（已有 header）
- 搜索框（保留）
- 主体：卡片网格（CSS Grid，自适应列数，2-4 列）
- 每张卡片：
  - 顶部：文件图标 + 类型标签（fact/preference）
  - 标题：displayTitle(relativePath)
  - 摘要：summary（前 2 行）
  - 底部：日期（formatDate(mtimeMs)）+ 实体标签（最多 3 个，溢出显示 +N）
- 点击卡片：右侧弹出预览面板（保留现有预览逻辑）
- 空态：带图标的友好空态（参考专家模式空态）

### 2.2 辅助函数
- `displayTitle()` — 从路径提取可读标题（已有，保留）
- `formatDate()` — mtimeMs → 短日期（已有，保留）
- `parseFrontmatterMeta()` — 从文件内容提取元数据（client 端用于预览面板）

### 2.3 locales 新增 key（zh/en 配对）
- `empty.title` — 「暂无记忆笔记」/ 'No memory notes yet'
- `empty.hint` — 「对话中提到的事实和偏好会自动记录在这里」/ 'Facts and preferences mentioned in conversations will be recorded here'
- `card.untitled` — 「无标题」/ 'Untitled'
- `card.created` — 「创建于 {date}」/ 'Created {date}'
- `card.kind.fact` — 「事实」/ 'Fact'
- `card.kind.preference` — 「偏好」/ 'Preference'
- `preview.title` — 「笔记预览」/ 'Note preview'

### 2.4 CSS 新增类
- `.cardGrid` — Grid 布局容器
- `.noteCard` — 单张卡片
- `.cardMain` — 卡片主体
- `.cardTop` — 卡片顶部（图标+类型）
- `.cardTitle` — 标题
- `.cardExcerpt` — 摘要
- `.cardMeta` — 底部元数据
- `.entityTag` — 实体标签
- `.emptyState` / `.emptyIcon` / `.emptyTitle` / `.emptyHint`

---

## 三、测试

### 3.1 host 端测试（`project-memory`）
- `listLibraryFiles` 只返回当前 workspace 的笔记 + user 级笔记
- 其他 workspace 的笔记被过滤掉
- frontmatter 解析正确（kind/createdAt/entities/summary）
- 无 frontmatter 的文件降级显示（字段留空）
- `../` 穿越仍然被拒绝

### 3.2 client 端测试（`client-ui-project-memory`）
- 卡片网格渲染正确
- 空态显示
- 点击卡片打开预览
- 搜索功能正常
- UNAVAILABLE 态显示

---

## 四、验收标准
1. 侧边栏点击「记忆库」弹出居中 Modal
2. Modal 内显示卡片网格，每张卡片有标题/日期/摘要/类型标签
3. 只显示当前工作区（dsh-devframe）的 2 个 project 笔记 + 1 个 user 笔记
4. 其他工作区的笔记不出现
5. 搜索、预览、复制路径、引用到对话功能正常
6. host 端 `test:coverage` 每文件 100%
7. client 端测试全绿
8. `pnpm run typecheck` + `pnpm run lint` 通过

---

## 五、范围排除
- 不做写入/编辑功能（writeEnabled 配置已有，但 UI 不暴露）
- 不做最近访问/Vault 选择 UI
- 不做 D7/D8 相关功能
- 不改 shadow-router / shadow-bridge
