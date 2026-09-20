# 记忆库入口改造：侧边栏常驻卡片 → 专家模式式弹窗

## 1. 背景与目标

用户反馈：当前「记忆库」在侧边栏底部是一个常驻面板（标题 + 刷新按钮 + 搜索框 + 文件列表 + 预览），占用大量侧边栏空间。期望改为与「专家模式」一致的交互模式：**侧边栏只放一个小按钮入口，点击后弹出模态弹窗管理库内容**。

## 2. 现状对比

| 维度 | ExpertTeamCard（目标模式） | LibraryCard（现状） |
|---|---|---|
| 侧边栏渲染 | 42px 高 trigger 按钮（图标+标签+运行数 badge） | 完整面板（header+搜索+列表+预览，自适应高度） |
| 数据加载 | 挂载时即 load() 快照 | 挂载时即 load() 快照 |
| 内容容器 | `<Modal headless>` 内渲染 ExpertCenter | 直接在侧边栏 DOM 内渲染 |
| 触发交互 | 点击 trigger → setOpen(true) + refresh() | 无 trigger 概念，常驻可见 |
| Modal 关闭 | onClose → setOpen(false) | 无 Modal |

## 3. 改造方案

### 3.1 LibraryCard.tsx 重构

**外层组件（LibraryCard）**：
- 增加 `open: boolean` state（初始 false）
- 初始不调用 `load()`（改为点击 trigger 时才加载，与 ExpertTeamCard 一致）
- 渲染结构：
  ```tsx
  <>
    <div className={css.root}>
      <button className={css.trigger} onClick={() => { setOpen(true); void refresh() }}>
        <IconDatabaseOutline16 />
        {wide && <span className={css.triggerLabel}>{t('trigger.label')}</span>}
        {wide && fileCount !== undefined && <span className={css.count}>{fileCount}</span>}
      </button>
    </div>
    <Modal open={open} onClose={() => setOpen(false)} title={t('center.title')} headless className={css.centerModal}>
      <LibraryPane ... />  {/* 现有内容搬进 Modal */}
    </Modal>
  </>
  ```
- `fileCount` 从 snapshot 读取，显示在 trigger badge 上（初始 0 / 未加载时不显示 badge）

**LibraryPane 保持不变**（presentational 组件，所有现有测试用例继续适用），仅调整 CSS 使其在 Modal 内合理布局。

### 3.2 CSS 调整（LibraryCard.module.css）

新增（从 ExpertTeamCard 复制并简化）：
- `.root`：`position: relative; flex: none; width: 100%; height: 42px; margin: 8px 0 0;`
- `.trigger`：与 ExpertTeamCard trigger 一致
- `.triggerLabel`：ellipsis
- `.count`：badge 样式
- `.centerModal`：Modal 容器（从 ExpertTeamCard 复用类似尺寸）

调整现有：
- `.pane`：去掉 `min-height: 0` 的侧边栏约束，改为在 Modal 内 flex 布局（max-height 调整为 Modal 内容区高度）
- `.fileList` 的 `max-height: 280px` 增大（Modal 空间更充裕）

### 3.3 locales.ts 新增文案

```
'center.title': '记忆库' / 'Library'
```
（trigger.label 复用）

### 3.4 测试更新（library-card.client.spec.tsx）

现有用例需要适配新的交互模式：
1. **初始渲染**：只应看到 trigger 按钮（aria-label="打开记忆库"），不应看到文件列表/搜索框
2. **点击 trigger**：触发 load()，文件列表和搜索框出现
3. 其余用例（搜索、预览、复制路径、引用、UNAVAILABLE 空态、错误态）——在点击 trigger 之后执行，断言不变
4. **Modal 关闭**：点击关闭按钮后，pane 内容消失，回到 trigger
5. **badge**：文件数显示在 trigger 上

### 3.5 mount.ts 不变

slot 注册逻辑不变（仍是 `sidebar.footer.action` / id `project-library` / order 25）。

## 4. 验收标准

1. 侧边栏底部「记忆库」显示为单行按钮（图标 + 「记忆库」标签 + 文件数 badge），不再展开面板
2. 点击按钮弹出居中模态弹窗，包含搜索/列表/预览全部功能
3. 再次点击外部或关闭按钮弹窗消失
4. 弹窗内功能与改造前完全一致（搜索、预览、复制路径、引用到对话、UNAVAILABLE 空态）
5. 初始不调用 load()（侧边栏安静，不发 RPC）；点击 trigger 时才加载
6. typecheck / lint / 单测全绿
7. 桌面客户端重启后视觉确认

## 5. 范围与边界

- 不改 host 端 Remote / Gateway 任何代码
- 不改 mount.ts 的 slot 注册参数
- 不改 reference.ts（引用到对话逻辑）
- 不改 locales 现有 key（只新增 `center.title`）
- LibraryPane 的 props 接口不变

## 6. 风险

- Modal 组件在 jsdom 中的行为需验证（ExpertTeamCard 已有测试先例，风险低）
- 现有测试断言需要全部适配"先点击 trigger 再断言"的模式
