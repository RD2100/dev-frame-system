# 影子会话修复计划 v2

## 目标

修复影子会话"历史加载失败：network error (gateway/internal)"的问题，实现"客户端安装完插件后能直接投入使用"。

## 审核修正说明

根据子agent审核意见，v1 计划有以下问题：
1. 自动创建会话的功能其实**已经存在**于 `ShadowAgent.ensureOnce()` 里，不需要新开发
2. 建会话的职责应该在 shadow-agent，不是 shadow-router
3. 移除旧的 `shadowSessionId` 会导致影子彻底打不开
4. 旧会话没有 cwd 的问题**已有现成修复路径**——`attachSessionCwd` 会自动修复
5. "network error gateway/internal" 可能是上游 LLM 网关的问题，不是本地会话的问题

## 新方案

### 第一步：验证现有修复路径

**先不动代码**，先验证现有的 `attachSessionCwd` 机制是否已经能修复旧会话的 cwd 问题。

**操作**：
1. 重启客户端
2. 点击影子按钮
3. 观察：
   - 旧会话 `session-0e48cb66-...` 是否自动获得了 cwd `D:/shadow-trial`？
   - 历史加载是否正常？

**预期结果**：如果 `attachSessionCwd` 工作正常，旧会话的 cwd 会被自动修复，历史应该能正常加载。

### 第二步：如果第一步失败，换全新会话

如果旧会话历史还是加载失败，说明旧会话的数据确实损坏了，我们需要**换一个全新的会话**。

**操作**：
1. 修改配置文件 `C:\Users\25313\.dsh\profiles\web\devframe-deployment.yml`
2. 把 `shadowSessionId` 改成一个新的 UUID（比如 `session-new-shadow-...`）
3. 保留其他配置不变（`designatedCwd`、`authorizedRoots` 等）
4. 重启客户端
5. 点击影子按钮，验证新会话能正常打开

**原理**：`ShadowAgent.ensureOnce()` 会检测到新 id 对应的会话不存在，自动 `agents.create` 创建一个新的活 Agent，cwd 用 `authorizedRoots[0]`（`D:/dsh-devframe`）。

### 第三步：如果新会话的 cwd 不对，修正 cwd 来源

如果新创建的影子会话 cwd 是 `D:/dsh-devframe`，但我们想要的是 `D:/shadow-trial`，那需要修改 `shadow-agent.ts:370`，把新建会话的 cwd 从 `authorizedRoots[0]` 改成 `designatedCwd`。

**改动范围**：
- 文件：`packages/experimental/shadow-controller/src/shadow-agent.ts`
- 位置：第 370 行附近
- 改动：新建会话时，cwd 优先用 `designatedCwd`，fallback 到 `authorizedRoots[0]`

**注意**：这是一个明确的行为变更，需要更新相关测试。

## 范围

**做**：
- 验证现有 `attachSessionCwd` 机制
- 必要时换全新的 shadowSessionId
- 必要时修正新建会话的 cwd 来源

**不做**：
- 不把建会话逻辑搬进 shadow-router
- 不做运行时回写配置文件
- 不做会话历史迁移/合并

## 验收标准

1. 重启客户端后，点击影子按钮
2. 打开的影子会话能正常加载（没有"历史加载失败"错误）
3. 会话有正确的 cwd
4. 影子里的四个工具（read/write/edit/spawn_agent）能正常工作
5. 重启后影子会话保持不变（不会每次都新建）
