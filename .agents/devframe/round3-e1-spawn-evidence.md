# DevFrame Round-3 E1 日志证据提取（spawn 尝试原文）

G5 产出。证据源：E1 执行 Agent 会话日志 `C:\Users\25313\.dsh\sessions\--D-dsh-devframe--\66e9cb16-d533-4361-ae11-50a01541e67e\session.jsonl.zstd`（多帧 zstd 容器，2067 帧 / 2657 事件，解压 1,229,898 字节）。提取方法：按 `packages/session/session-persistence-jsonl/src/zstd.ts` 的 `scanZstdFrames` 结构扫描逐帧 `zlib.zstdDecompressSync` 解码（Node 一次性 API 只解首帧，必须逐帧切片）。

## 一、spawn 尝试原文（逐字，未删改）

### 1. E1 调用 subagent 工具（seq 11498）

```json
{"description":"Spawn capability probe","prompt":"Capability probe only. Do not read files, run commands, or start any work. Immediately reply with the single word: done.","run_in_background":true}
```

工具结果（逐字）：

```text
started subagent 86de844b-1748-4637-9238-c1b8f2b121f8
```

（`isError: false`；callId `call_e288305f9b8946088533d647`）

### 2. E1 中断该子 Agent（seq 11791）

```json
{"agent_id":"86de844b-1748-4637-9238-c1b8f2b121f8"}
```

工具结果（逐字）：`interrupt requested for agent 86de844b-1748-4637-9238-c1b8f2b121f8`

### 3. E1 复核子 Agent 状态（seq 22405，list_agents）

工具结果（逐字）：`86de844b-1748-4637-9238-c1b8f2b121f8 [ready] — Spawn capability probe`

## 二、证据解读（按日志如实定性，不外推）

1. E1（depth 2，会话头 `parentSession: ca378724-8de0-4c17-94e0-05aa828c1366`，即由 G2 前任组长创建于 toolFilter 强制落地之前）的 `subagent` 调用**成功**：depth 2 → 3 派生 probe 存活。这就是台账所记「probe 于 depth 3 存活 = 默认无过滤时执行 Agent 可建子 Agent（策略缺口实证）」的原文证据。
2. E1 日志中**不含** spawn 被拒原文（其唯一一次 spawn 成功了）；执行器级拒绝的首要点证据是 G2 的 308 行 enforcement 锚定测试（`dea960b656`/`c64497a257`）与 E1 后继交付 `c10127a5f5`（+57 行）锚定的 driver 行为，均已并入 main（`4a9aed6e08`/`6ba3e5f824`）。
3. 会话头实测字段：`origin: subagent`、`delegationDepth: 2`、`agentPreset: standard`——与 G1 身份链交付一致。
4. E1 全部 61 次工具调用中 spawn 族仅上述 3 次（subagent ×1、interrupt_agent ×1、list_agents ×1），无其他派生尝试。
