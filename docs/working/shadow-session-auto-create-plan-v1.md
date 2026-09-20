# 影子会话自动创建计划 v1

## 目标

创建一个全新的影子会话，有正确的 cwd，实现"客户端安装完插件后能直接投入使用"的目标。

## 当前问题

- 旧的影子会话 `session-0e48cb66-...` 是在 workspace 配置之前创建的，没有 cwd
- 点击影子后，能打开这个会话，但历史加载失败：`network error (gateway/internal)`
- 根本原因：旧会话的历史数据和当前 workspace 配置不兼容

## 方案

在 shadow-router 插件启动时，如果检测到配置的 `shadowSessionId` 对应的会话不存在或有问题，就**自动创建一个新的影子会话**，并把它的 ID 更新到配置里。

这样用户安装完插件后，第一次点击影子时会自动创建一个全新的、有正确 cwd 的影子会话，不需要手动配置。

## 具体步骤

### 1. 修改 shadow-router 插件

**文件**：`packages/experimental/shadow-router/src/service.ts`

**改动**：
- 在 shadow-router 启动时，检查配置的 `shadowSessionId` 是否有效
- 如果无效（会话不存在、没有 cwd、或加载失败），自动创建一个新的会话
- 新会话的 cwd 用 `designatedCwd`
- 把新会话的 ID 写回配置文件（持久化）

### 2. 修改 shadow-agent 插件

**文件**：`packages/experimental/shadow-controller/src/shadow-agent.ts`

**改动**：
- 确保 ShadowAgent 正确处理新创建的会话
- 新会话启动时，自动加载 system prompt

### 3. 更新配置文件

**文件**：`C:\Users\25313\.dsh\profiles\web\devframe-deployment.yml`

**改动**：
- 移除旧的 `shadowSessionId`（让系统自动创建新的）
- 保留 `designatedCwd: 'D:/shadow-trial'`
- 保留 `authorizedRoots`

### 4. 验证

- 重启客户端
- 点击影子按钮
- 验证：打开的是一个新会话（不是旧的那个），有正确的 cwd，历史加载正常（空会话）

## 范围

**做**：
- 自动创建影子会话
- 持久化新会话 ID 到配置文件
- 确保新会话有正确的 cwd

**不做**：
- 不迁移旧会话的历史数据
- 不做会话恢复/合并功能
- 不做 UI 上的"重新创建影子会话"按钮

## 验收标准

1. 重启客户端后，点击影子按钮
2. 打开的是一个新的、空的会话（不是旧的那个）
3. 会话的 cwd 是 `D:/shadow-trial`
4. 历史加载正常（显示空会话，没有报错）
5. 新会话 ID 被持久化到配置文件里，下次重启还是这个会话
