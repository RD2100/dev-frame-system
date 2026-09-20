# #7 记忆库弹窗改进：修路径 bug + 专家模式风格卡片 UI

## 背景

用户反馈记忆库弹窗太简陋（只有搜索框+空提示），且显示「0 个文件」。
已定位根因：
- **Bug**：`library.ts:95` 的 `isForbiddenName` 把 `devframe-memory` 目录名硬编码为 forbidden，而所有记忆笔记都写在 `vault/devframe-memory/` 下，导致 walk 直接跳过该目录，列出 0 个文件。
- **UI 简陋**：当前弹窗只有单行搜索框 + 文件列表 + 右侧预览，没有视觉层次、没有卡片设计、没有元数据展示。

## 设计参考

- **专家模式弹窗**：顶部标签页 + 搜索框 + 分类标签 + 排序 + 卡片网格（每张卡片有图标/标题/描述/标签）
- **Obsidian 风格**：笔记卡片显示 frontmatter 元数据（kind、entities、createdAt），正文摘要预览，目录树导航

## 范围

### 修 bug（host 端）
- [ ] `library.ts:91-100` `isForbiddenName`：删除 `if (trimmed === 'devframe-memory') return true` 这一行
- [ ] 原因：devframe-memory 是用户的记忆笔记所在目录，不是安全敏感目录；排除它等于把记忆库本身藏起来
- [ ] .obsidian 等 dot 目录仍然被排除（starts with '.'），不变

### UI 改进（client 端）
1. **弹窗布局**：从「左列表+右预览」改为专家模式风格的**卡片网格 + 点击展开详情**
2. **卡片内容**：
   - 顶部：kind 图标（fact/event/source 等，用不同颜色区分）
   - 标题：从正文第一行提取（或用 relativePath 美化）
   - 摘要：正文前 100 字符
   - 元数据行：createdAt 日期 + entities 标签
   - 底部操作：复制路径、引用到对话
3. **顶部栏**：
   - 左侧：标题「记忆库管理」 + 文件数 badge
   - 中间：搜索框（文件名+内容）
   - 右侧：刷新按钮 + 关闭按钮
4. **空态**：不再只显示「记忆库中没有文件」，改为有插画/图标的友好空态
5. **预览**：点击卡片后在弹窗底部/右侧展开详情面板（markdown 渲染 + 操作按钮）

## 验收标准

1. 打开记忆库弹窗后能看到 `devframe-memory/` 下的 3 个 .md 笔记卡片
2. 每张卡片显示 kind 类型、摘要、创建日期、entities 标签
3. 搜索能按文件名和内容过滤
4. 点击卡片展开预览（正文 + 复制路径 + 引用按钮）
5. 单测全绿（含新卡片渲染、空态、搜索过滤用例）
6. typecheck + lint 通过
7. 重新打包 client bundle 后浏览器能看到新 UI
