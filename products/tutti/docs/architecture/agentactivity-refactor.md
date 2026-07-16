# agentactivity 公共包改造方案

> 目标：将 `packages/agentactivity` 整理为对外发布的公共包，明确三个核心接口边界，解决流式消息远端同步的频繁请求问题。

---

## 背景

`packages/agentactivity/daemon` 目前存在几个问题：

1. **类型与实现混在一起**：`client.go` 同时包含领域类型和 HTTP 实现，难以被外部引用。
2. **接口分散**：`SessionActivityReporter` 在 `compat.go`，`AgentActivityRepository` 在 `service.go`，没有统一的对外入口。
3. **流式消息无合并**：`bridge/agent_activity.go` 每个 chunk 启动一个 goroutine，100 个 chunk → 100 个远端请求。
4. **`shared/` 命名歧义**：包含的是事件类型定义，应命名为 `events/`。

---

## 目录结构

### 改造前

```
packages/agentactivity/
└── daemon/
    ├── client.go          # 领域类型 + HTTP 实现混合
    ├── compat.go          # SessionActivityReporter 接口
    ├── service.go         # AgentActivityService + 仓储接口
    ├── ingress/
    ├── hostquery/
    └── shared/
        ├── activity_types.go
        └── context/
```

### 改造后

```
packages/agentactivity/
├── daemon/                # Go daemon 上下文
│   ├── reporter.go        # Interface 1：上报接收契约
│   ├── repo.go            # Interface 2：仓储契约
│   ├── view.go            # Interface 3：View 协议
│   ├── stream_writer.go   # 流式消息辅助类型（helper）
    ├── types.go           # 所有领域类型（从 client.go 拆出）
    ├── client.go          # HTTP 实现（只保留网络层）
    ├── service.go
    ├── ingress/
    ├── hostquery/
│   └── events/            # shared/ 改名
│       ├── types.go       # activity_types.go 改名
│       └── context/
└── renderer/              # Renderer/React 上下文
```

---

## Interface 1 — Reporter（`reporter.go`）

对外暴露的上报接收入口，内部包含本地优先策略和异步队列，调用方无需感知。

```go
package agentactivity

import "context"

// ActivityReporter 是 ACP 路径（实时每帧）的上报契约。
type ActivityReporter interface {
    Report(ctx context.Context, input ReportActivityInput) error
}

// SessionActivityReporter 是 ingress 层的细粒度上报契约。
type SessionActivityReporter interface {
    ReportSessionState(context.Context, ReportSessionStateInput) (ReportSessionStateReply, error)
    ReportSessionMessages(context.Context, ReportSessionMessagesInput) (ReportSessionMessagesReply, error)
}
```

两条上报路径说明：

| 路径               | 接口                      | 特点                        |
| ------------------ | ------------------------- | --------------------------- |
| ACP（JSON-RPC 流） | `ActivityReporter`        | 实时，每个 ACP 事件触发一次 |
| gRPC ingress       | `SessionActivityReporter` | 批量，工具调用结束后触发    |

两者在 daemon 内部都通过 `ReportActivityAsSessionUpdates` 适配，外部不需要感知区别。

---

## Interface 2 — Repo（`repo.go`）

业务层自己提供实现，daemon 只依赖接口。

```go
package agentactivity

import "context"

// AgentActivityRepository 是持久化层契约，业务方自行实现。
type AgentActivityRepository interface {
    AgentActivityReadRepository
    ReportSessionState(ctx context.Context, input ReportSessionStateInput) (ReportSessionStateReply, error)
    ReportSessionMessages(ctx context.Context, input ReportSessionMessagesInput) (ReportSessionMessagesReply, error)
}

type AgentActivityReadRepository interface {
    ListAgents(ctx context.Context, roomID string) (*WorkspaceAgentSnapshot, error)
    ListSessionMessages(ctx context.Context, input ListSessionMessagesInput) (*ListSessionMessagesReply, error)
}

// AgentActivitySyncStateStore 是本地同步状态的持久化契约（可选，用于断线续传）。
type AgentActivitySyncStateStore interface {
    LoadRoomSyncStates(ctx context.Context, roomID string) (map[string]WorkspaceAgentSyncState, error)
    SaveAgentSyncState(ctx context.Context, roomID string, state WorkspaceAgentSyncState) error
    DeleteAgentSyncState(ctx context.Context, roomID string, agentSessionID string) error
}
```

这三个接口已存在于 `service.go`，只做移位，不改签名。

---

## Interface 3 — View（`view.go`）

daemon 持有 `SnapshotListener`；业务方实现 bridge，bridge 负责 diff 后调用细粒度的 `AgentActivityView` 方法。官方渲染层未来提供，用户可自行实现。

```go
package agentactivity

// SnapshotListener 是 daemon 在本地状态变更时回调的接口。
// bridge 接收完整快照，自行 diff 后调用细粒度的 AgentActivityView 方法。
type SnapshotListener interface {
    OnSnapshotChanged(roomID string, snapshot WorkspaceAgentSnapshot)
}

// AgentActivityView 是渲染层协议，支持细粒度局部更新。
type AgentActivityView interface {
    OnSessionAdded(roomID string, session WorkspaceAgentSession)
    OnSessionUpdated(roomID string, session WorkspaceAgentSession)
    OnSessionRemoved(roomID string, agentSessionID string)

    // 流式增量更新，每个 chunk 都会触发
    OnMessageUpdated(roomID string, agentSessionID string, message WorkspaceAgentSessionMessage)

    OnPresenceChanged(roomID string, presences []WorkspaceAgentPresence)
}
```

### Bridge 层职责（业务方提供，不在 daemon 包内）

```go
type myBridge struct {
    view     agentactivity.AgentActivityView
    lastSnap map[string]agentactivity.WorkspaceAgentSnapshot
}

func (b *myBridge) OnSnapshotChanged(roomID string, snap agentactivity.WorkspaceAgentSnapshot) {
    prev := b.lastSnap[roomID]
    b.lastSnap[roomID] = snap
    diffAndDispatch(b.view, roomID, prev, snap)
}
```

如果 View 更新开销大，debounce 在 bridge 内部加，daemon 不干预。

---

## Runtime Reporter 的流式合并

### 当前问题

ACP streaming 每个 chunk 都可能生成一次消息更新；如果逐条远端提交，100 个 chunk 会产生 100 个远端请求。

### 当前实现

本地应用路径由 `Store.ApplyEvents` / `Store.ApplyActivity` 立即更新内存快照并触发 listener。远端提交由 runtime reporter 负责，流式消息合并在 `packages/agent/daemon/runtime/report_coalescer.go` 内完成，不再经过 `activity/dispatch` 包。

```go
func (c *streamingReportCoalescer) add(request reportRequest) []reportRequest {
    sessionKey := reportCoalesceSessionKey(request.report)
    if isCoalescibleStreamingReport(request.report) {
        c.merge(sessionKey, request)
        c.ensureTimer()
        return nil
    }
    flushed := c.flushSession(sessionKey)
    return append(flushed, request)
}
```

### 合并粒度

合并只针对同 workspace、同 origin、同 agent session 的 streaming text/reasoning message update；终态消息、state patch、timeline item 会先 flush 同 session 的 pending streaming update，再独立提交。

| 路径     | 触发 View           | 远端同步                         |
| -------- | ------------------- | -------------------------------- |
| 本地应用 | 每个 chunk 立即触发 | —                                |
| 远端同步 | —                   | runtime coalescer 合并后批量发送 |

本地优先的核心价值是 UI 始终响应；合并只针对远端，两者不冲突。

---

## MessageStreamWriter Helper（`stream_writer.go`）

不改接口，给调用方提供流式写入的便利封装。

```go
package agentactivity

import "context"

// MessageStreamWriter 封装流式消息的重复调用，调用方无需管理 messageID 和 append 语义。
type MessageStreamWriter struct {
    reporter       SessionActivityReporter
    workspaceID    string
    agentSessionID string
    messageID      string
    source         EventSource
}

func NewMessageStreamWriter(
    reporter SessionActivityReporter,
    workspaceID, agentSessionID, messageID string,
    source EventSource,
) *MessageStreamWriter {
    return &MessageStreamWriter{
        reporter:       reporter,
        workspaceID:    workspaceID,
        agentSessionID: agentSessionID,
        messageID:      messageID,
        source:         source,
    }
}

func (w *MessageStreamWriter) Write(ctx context.Context, chunk string) error {
    _, err := w.reporter.ReportSessionMessages(ctx, ReportSessionMessagesInput{
        WorkspaceID:    w.workspaceID,
        AgentSessionID: w.agentSessionID,
        Source:         w.source,
        Updates: []WorkspaceAgentSessionMessageUpdate{
            {MessageID: w.messageID, ContentDelta: chunk},
        },
    })
    return err
}

func (w *MessageStreamWriter) Close(ctx context.Context, status string) error {
    _, err := w.reporter.ReportSessionMessages(ctx, ReportSessionMessagesInput{
        WorkspaceID:    w.workspaceID,
        AgentSessionID: w.agentSessionID,
        Source:         w.source,
        Updates: []WorkspaceAgentSessionMessageUpdate{
            {MessageID: w.messageID, Status: status},
        },
    })
    return err
}
```

---

## 改造顺序

| 步骤 | 内容                                                      | 风险                       |
| ---- | --------------------------------------------------------- | -------------------------- |
| 1    | `client.go` 拆分为 `types.go` + `client.go`               | 低，纯文件拆分，无逻辑变更 |
| 2    | `shared/` 改名为 `events/`，更新所有 import               | 低                         |
| 3    | 三个根包接口文件（`reporter.go` / `repo.go` / `view.go`） | 低，大部分已存在，只是移位 |
| 4    | runtime reporter 增加 streaming report coalescer          | 中，需要覆盖流式场景的测试 |
| 5    | `stream_writer.go` helper                                 | 低，纯新增                 |
