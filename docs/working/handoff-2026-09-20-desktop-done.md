# 交接文档：DSH 桌面客户端 + 自包含分发

**日期**：2026-09-20
**分支**：`feat/desktop-quality-fixes`（已 push，PR #13 已开）
**Base**：`reference/dev-frame-system-dsh`

---

## 一、当前状态

### 已完成

| 事项 | Commit | 说明 |
|---|---|---|
| 桌面客户端启动排障（3 层根因） | `e5f975491f` | 悬空符号链接 + electron 二进制版本不匹配 + host 旧产物/overlay 禁 web 服务 |
| 记忆库管理修复 | `c289041284` | 去掉 `library.ts` 对 `devframe-memory/` 的排除，UI 能显示自动记忆笔记 |
| project-controller 打包白名单 | `47d8c3bebf` | files 改 glob，包含 tsdown hash 分块 |
| 工作树分批提交 | `b9b612774f` → `91b590e14b` | 5 批提交，工作树 0 残留 |
| vendor/README.md 补条目 | `f1758faeae` | 加 dsh-mobile-pairing 行，third-party notices 钩子通过 |
| Push + PR | — | PR #13: https://github.com/RD2100/dsh-devframe/pull/13 |

### 自包含试发验证结果

- 20/20 包打 tarball → 干净目录安装 → ESM import 成功
- peer 单例正常（cordis/schemastery/cosmokit/dsh-brand 全在 peerDependencies）
- fail-loud 守卫生效（缺 peer 时报 ERR_MODULE_NOT_FOUND 点名缺失包）
- 版本号统一 0.1.6-alpha.1

---

## 二、桌面客户端运行状态

- **启动脚本**：`D:\dsh-devframe\.desktop-devframe-staging\dsh-client-launch.ps1`
- **运行日志**：`.desktop-devframe-staging\dsh-client-run.log`
- **运行时项目**：`D:\dsh-devframe\apps\desktop\.desktop-build\development\project\`
- **webserver**：127.0.0.1:3080
- **pairing 网关**：127.0.0.1:55733（Quick Tunnel）
- **Electron 二进制**：44.4.2（从 npmmirror 下载，旧 44.0.0 备份为 dist.44.0.0.bak）
- **Electron 进程**：4 个（main/renderer/host/preload）

### 已确认正常

- 聊天主界面
- 影子（shadow）对话
- 专家团（expert-team）
- 记忆库管理对话框（3 条记忆显示：1 事实 + 2 偏好）

---

## 三、未完成 / 待推进

### 1. 用量统计插件排查（当前进行中）

**问题**：用户反馈"原来网页中还有插件没有安装到 DSH 中，比如说用量统计插件"。

**已排查**：
- Desktop 加载 bundle：`dsh-base` + `dsh-web-app` + `devframe-profile` + `dsh-mobile-pairing`
- Desktop overlay patch 只禁用了 `client-hmr` 和 `directory-picker`（用 native 替代）
- `session-stats`（用量统计 host 侧）和 `ui-trajectory`（TurnUsagePanel UI）都随 web-app bundle 加载，未被禁用
- **结论**：插件层面已加载，看不到可能是渲染问题或 UI 入口问题

**下一步**：
- 确认用户具体在哪个界面看不到用量统计（聊天主界面？设置页？）
- 检查 Electron renderer 里 `TurnUsagePanel` 是否挂载
- 检查 `session-stats` 服务是否实际启动并产生数据
- 可能需要看 renderer console 报错

### 2. agent-dispatch / command-goal-binding 的 files 白名单

当前也是手写模式，虽然暂时没有 hash 分块所以没炸，但 tsdown 一旦代码分割就会复现 project-controller 的问题。建议后续一起改 glob。

### 3. vendor/README.md 的 @dsh-mobile/pairing 信息

commit hash 写的是 `91b590e14b...`（提交时的 HEAD），后续如果这个包更新需要同步。

### 4. 上一阶段 WIP

已全部提交（5 批），工作树干净。

---

## 四、关键文件路径

### 配置
- `apps/desktop-host/config/desktop.cordis.patch.yml` — Desktop overlay patch（禁 client-hmr/directory-picker，加 native 替代）
- `apps/desktop/.desktop-build/development/project/cordis.patch.yml` — 运行时 profile patch（expert-team/project-memory/shadow-router/command-goal-binding/agent-hierarchy/shadow-bridge/ui-shadow-entry/dsh-mobile-pairing）
- `apps/desktop/.desktop-build/development/project/desktop.cordis.yml` — composition root（空 `[]`）
- `packages/experimental/devframe-profile/cordis.patch.yml` — DevFrame profile 层

### 插件源码
- `packages/experimental/project-memory/src/library.ts` — 记忆库列表（刚改）
- `packages/experimental/project-controller/package.json` — files glob（刚改）
- `packages/client/ui-chat/src/client/chat/TurnUsagePanel.tsx` — 用量统计 UI
- `packages/bundle/web-app/cordis.patch.yml` — Web bundle 完整插件清单

### 构建
- desktop-host：`tsc -b apps/desktop-host` + `cd apps/desktop-host && pnpm exec tsdown`
- project-memory：在包目录跑 `pnpm run build`（如果需要）

---

## 五、已知问题

1. **GitHub push 需要代理**：SSH 被墙，已配置 `http.proxy=http://127.0.0.1:7897`，origin 已从 SSH 改为 HTTPS
2. **pre-commit 钩子**：`vendor/README.md` 缺条目已补，但 `translation pairing` 对其他未跟踪文件（docs/working/ 等）仍可能报错——这些是 pre-existing 问题，不在本次范围
3. **Electron 下载**：GitHub 被墙，启动脚本已加 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`

---

## 六、用户偏好（必须遵守）

1. 开发流程：先出计划 → 子 agent 审核 → 执行 → 子 agent 验收，不跳步
2. 每完成一个版本/阶段就 git commit，不攒多个版本
3. Git push/PR 必须用户明确授权
4. 排障直击根因和真实报错，改完用真实界面截图验证
5. UI/交互对标成熟聊天产品（微信/豆包）
6. 完全访问模式，先落地不满意回滚
7. 讨论的是桌面客户端版本，不是网页版

---

## 七、PR 信息

- **PR #13**：https://github.com/RD2100/dsh-devframe/pull/13
- **Branch**：`feat/desktop-quality-fixes`
- **Commits**：13 笔
- **Base**：`reference/dev-frame-system-dsh`
- **状态**：已推送，待 review/merge
