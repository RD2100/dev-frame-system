# 影子会话修复计划 v3

## 目标

修复影子会话问题，实现"客户端安装完插件后能直接投入使用"。

## 审核修正说明

根据子agent审核意见，v2 有以下问题：
1. **执行顺序反了**：应该先改 cwd 来源代码，再换 shadowSessionId。否则新会话第一次启动就已经带上错误的 cwd 了
2. **第一步预期混淆了两件事**：`attachSessionCwd` 只补 cwd，不碰历史内容。"network error gateway/internal" 很可能是上游 LLM 网关的问题
3. **验收标准工具名写错了**：影子会话里 read/write 是 unknown tool，只有四个对话工具可用

## 执行步骤（严格串行）

### 第一步：修正新建会话的 cwd 来源

**文件**：`packages/experimental/shadow-controller/src/shadow-agent.ts`

**改动**：
- 位置：第 370 行附近（新建会话时设置 cwd 的地方）
- 改动：新建会话时，cwd 优先用 `designatedCwd`，fallback 到 `authorizedRoots[0]`
- 同时更新对应的注释和测试

**为什么先做这步**：
- `ensureOnce` 在首次用新 id 启动时就会 `agents.create` 并把 cwd 写进会话头
- `attachSessionCwd` 是单向的，已有 cwd 就拒绝执行
- 所以必须先改代码，再换 id，否则新会话第一次启动就带上错误的 cwd 了

### 第二步：换全新的 shadowSessionId

**文件**：`C:\Users\25313\.dsh\profiles\web\devframe-deployment.yml`

**改动**：
- 把 `shadowSessionId: session-0e48cb66-...` 改成一个新的 UUID
- 格式：`session-<uuid v4>`（比如 `session-a1b2c3d4-...`）
- 保留其他配置不变（`designatedCwd`、`authorizedRoots` 等）

**为什么换 id**：
- 旧会话 `session-0e48cb66-...` 的历史数据可能损坏了
- 用新 id 让 `ShadowAgent.ensureOnce()` 自动创建一个全新的活 Agent
- 新会话的 cwd 会用第一步修改后的逻辑（优先 `designatedCwd`）

### 第三步：重启客户端验证

**操作**：
1. 完全关闭 DSH 客户端
2. 重新启动
3. 点击影子按钮
4. 观察：
   - 是否打开了一个新的、空的会话？
   - 会话的 cwd 是否是 `D:/shadow-trial`？
   - 有没有"历史加载失败"的错误？

## 关于 "network error gateway/internal"

**单独排查**：
- 这个错误很可能是上游 LLM 网关的 HTTP 5xx 错误
- 不是本地会话数据损坏
- 如果换了全新会话后还是报这个错，说明是 API key 或网络问题，不是我们的代码问题

## 范围

**做**：
- 修改 `shadow-agent.ts:370`，新建会话时 cwd 优先用 `designatedCwd`
- 换全新的 `shadowSessionId`
- 验证新会话能正常打开

**不做**：
- 不把建会话逻辑搬进 shadow-router
- 不做运行时回写配置文件
- 不做会话历史迁移/合并
- 不迁移旧会话的数据

## 验收标准

1. 重启客户端后，点击影子按钮
2. 打开的是一个新的、空的会话（不是旧的那个）
3. 会话的 cwd 是 `D:/shadow-trial`
4. `shadowSetup` 安装的四个影子对话工具可调用
5. 重启后影子会话保持不变（不会每次都新建）
6. 没有"历史加载失败"的错误（如果还有 gateway error，那是上游 API 问题，不是本地代码问题）
