# Shadow Todo 看板 v2 实施计划 r3 — 独立第三方复评意见（通过）

- 待审计划：`docs/working/shadow-todo-board-v2-plan.zh.md`（front-matter status: draft-plan-r3，§3 回应表新增 r2 列）
- 历史意见：r1 打回（P0×2）、r2 打回（P1×5 收尾）
- 复评方式：两名评审员分别核对计划正文与源码；P1-3 的新源码论断由源码评审独立定位 typert 协议包核实。
- 复评日期：2026-09-20
- **结论：通过。** r2 的 5 条 P1 窄口全部落实到计划正文，P1-3 的源码论断经协议层独立核实成立；剩余 3 处为文档级笔误，不阻断执行，建议合并前顺手修掉。

---

## r2 五条 P1 复核结果

### P1-1 cwd 归一化 — 已落实（Q3 line 70）
三要素齐：host 在 `store.save`/算 digest/注册之前先 `realpathNormalize(cwd)`；写明 digest 对字面量 cwd 哈希（required-checks.ts:309）与 delivery-consumer:211 realpath 比较的分叉；junction 证据（development-project.ts:71 `symlinkSync(..., 'junction')`）。逻辑闭环。

### P1-2 beforePersist 接线 — 已落实（Q1 步骤 5 line 45）
逐字写成 `assign(worker.sessionId, { beforePersist: () => reCheck() })` → `startDevelopment(..., { beforePersist: () => reCheck() })`；reCheck 定义为重调 resolveTaskStartAuthority 比签名，对齐 task-consumer.ts:113/:116 的 unchanged 语义。controller.ts:400/:416 的 options 形参也确认支持 beforePersist。

### P1-3 typert caller 鉴权 — 论证成立（经协议层独立核实）
作者论断"typert 不向方法体暴露 caller 身份，方法内 caller 校验是伪校验"经三层证据证实：
- `TypertRemoteService` 构造只收 `(ctx, serviceKey, options)`（packages/typert/protocol/src/index.ts:155-169）；
- `@Remote` 装饰器只是原型 marker，不包方法不注入参数（同文件 :176-203）；
- 派发契约 `InvocationDescriptor`（types.ts:270-296）唯一注入的运行时参数是 `signal`（registry/src/service.ts:685-688 强制只能叫 'signal'），无 caller/callerSession 保留 wire 字段。
- 即便 request 自报 callerSessionId 也可被伪造，服务端无从证伪——"方法内校验"确实是伪校验。

等价防护三件套与现有 host-plane 写面同强：① 下游 `resolveTaskStartAuthority` 对未就绪任务 fail-closed（live controller / admission_open / 三 worktree 写锁 / 恰一 worker+lead），实际强于 `openProjectForHost`；② 模型工具面无 approve 工具（shadowAllowlistGuard）；③ `currentSession` 叠加已正确标注为条件增强（协议层确认该句柄不存在，实际不发生）。信任边界与现有 openProject/postMessage 一致。

### P1-4 #16 数据契约 — 已落实（阶段 C line 140；§4 line 199）
`ShadowBoardSnapshot` 加了 `branch?: string | null` + `lastActivityAt`；采集 = readBoard 对 developing/assigned task 的 worker worktree 只读 `git rev-parse --abbrev-ref HEAD`（5s 缓存、失败降级 null）；`lastActivityAt` 复用 `TaskRecord.updatedAt`。"最近命令"因无命令日志数据源明确撤掉，偏离在 §4 明记。

### P1-5 Goal 冷启动 — 已落实（阶段 B line 119-122）
主路径 = host 在 workspace binding 首次 ready 时 followup `/devframe-start`（带默认 objective 常量）；fallback = followup 后轮询 sessionProjections 60s 未达 admission_open 或命令不可用 → controller 用 create_goal 自主创建；并给了主路径优先理由。入口已定案，不再是冒烟临场挑。

## r2 P2 复核
- "种子"术语已统一（静态 seed 为空 + 运行时按 task 注册唯一一条 check）。
- 三处"执行时选定"（prompt 注入点、project-contracts link、agent-dispatch restate）保留为验证动作，未硬塞成决策。
- #15 时间阈值替代 token% 已在 §0/§7 记录。

---

## 剩余建议（合并前顺手修，不阻断）

1. **task-consumer 子区间正文与 §3 表不一致**：正文 Q1 line 39 写 authority :59-79、start 前置 :88-102；§3 line 185 写 authority :59-78、start 前置 :80-102。经源码仲裁：authority() 定义在 :59-78（:80 是调用点 `const initial = authority()`），start 前置断言块在 :88-102（worker 过滤 :88 起）。建议统一为 authority :59-78、start 前置 :88-102；正文的 :79 与 §3 的 :80 起点都偏一行。
2. **§3 标题陈旧**：line 156 仍作"评审意见回应表（修订 2 逐条回应）"，但表内已含 r2 行、整篇是 r3。改为"修订 3"。
3. **readBoard 降级位置自述越界**：§3 line 184 称该偏离"均已在 §0/§7/阶段 C 明记"，实际只在 Q2 line 58 与阶段 C line 140；§0 表与 §7 清单未列。偏离本身已记录、无 substance 缺失，把 §3 这行位置改对即可。
4. **行文小省略**：Q1 line 45 散文写 `assign(worker.sessionId, ...)` 省略首参 taskId；实现时按 controller.ts:400 传 `(taskId, worker.sessionId, {...})` 即可，非设计问题。
5. **诚实记录一条平台能力缺口（非本方案弱点）**：authority 门防"未就绪任务被推进"，但不区分"人类 vs 其他 host 组件"。真正 caller 级鉴权需 typert 传输层提供可信 caller 身份，协议层当前无此机制。建议在实现备注留一句，待平台补齐后再加。

---

## 终审结论
三轮评审：r1 打回（空 checkset 被 schema `.min(1)` 阻断 + approveTask 绕过 task-consumer 前置）→ r2 打回（cwd 归一化 / beforePersist / typert caller 论证 / #16 数据契约 / Goal 冷启动五条窄口）→ **r3 通过**。计划方向（路线 3 接 project-controller 核心件）正确，所有源码断言经独立核实，22 条 v1 硬伤全部有归宿，验收含 recorded-session 场景与 #13/#19/#20/#11/#21 点名用例。可进入实施。
