# B1 设计：v14 包挂入真实 dsh profile 全链（B 线组长 · v14-udeliver）

状态：design 定稿 v1（吸收 profile-probe Worker 结论）。基线：本树 codex/v14-udeliver-lead @ 6b31951491（含 main@908f627101 + compos 7c21ed0fc2 + goalstore cd676781c3）。

## 1. shipped profile 现状（读取记录，2026-09-06）

`apps/cli/config/examples/cordis/cordis.yml` 全文 19 行：web profile（dsh-base + dsh-web-app bundle 层）之上的 `--patch` overlay。现挂载面仅三行：webserver 钉 127.0.0.1:3081、insert `@deepseek-ai/dsh-cordis-host-runner`、insert `@deepseek-ai/dsh-tool-cordis`。**v14 三包（command-goal-binding / shadow-router / project-memory）零挂载**；依赖服务 `agentBindings`（@deepseek-ai/dsh-experimental-session-identity）在全 web 组合中未挂载（profile-probe 全仓 grep 证实）。

约束面（verify-cordis-config.ts validateAppResolution）：examples overlay 的裸插件名必须能从 `apps/cli/package.json` **dependencies**（devDependencies 不参与）或 bundle manifest deps 解析——现状四包全缺。

## 2. 挂载设计（shipped profile + 部署 overlay 两层）

### 2.1 shipped profile 增补（机器中立、安全默认，本组长唯一写入者串行收口）

新增 4 个 insert 行（顺序无加载语义，按依赖可读性排列）：

1. `session-identity`（@deepseek-ai/dsh-experimental-session-identity）——shadow-router 的 static inject 前置（service.ts:253 需 `agentBindings`）；自身安全（持久绑定域，仅在真实层级使用时写）。
2. `shadow-router`（@deepseek-ai/dsh-experimental-shadow-router）——全默认安全面：`authorizedRoots` 缺省 `[]`（fail-closed，不授权任何根）、不配 `shadowSessionId`（不指定 Shadow，四工具不装进任何会话）、`controllerProfile` 缺省 `devframe`（不存在则 project_open 使用期失败，不静默降级）。
3. `project-memory`（@deepseek-ai/dsh-experimental-project-memory）——`workspaceId: default`、`writeEnabled: false`、`userScopeEnabled: false`、不配 `vaultRoot`：工具报 MEMORY_UNAVAILABLE，加载安全（包内 cordis.patch.yml 注释明示该默认面）。
4. `command-goal-binding`（@deepseek-ai/dsh-experimental-command-goal-binding）——必填配置以 `!!js` 部署默认补齐（先例：base patch sandbox-policy 行 `!!js process.cwd()`，L218；`!!js` 仅允许在 plugin config 下）：`workspaceId: default`、`workspaceRoot: !!js process.cwd()`（启动项目语义=启动目录即绑定面）、`checks`（git diff --check 真实只读门，cwd `!!js process.cwd()`）、`taskIds: [devframe-goal]`、`maxAttempts: 3`。风险登记：数组内 `!!js` 无仓库先例（profile-probe 指出"未证实"）——以真实 `--dump-config` 探针实证插值是否到达数组内元素；若不到达，回退方案=该行移入部署 overlay（机器特定本就允许）。

配套机械增补（门禁驱动）：

- `apps/cli/package.json` dependencies += 四包精确名（@deepseek-ai/dsh-experimental-command-goal-binding / -shadow-router / -project-memory / -session-identity）。
- pnpm-lock importers 同步（importers-only 机械行；先例 compos 波 3 行机械 link）。
- `tsconfig.base.json` paths += command-goal-binding 映射（profile-probe：三包中唯一缺 paths 映射，会挂 validateSourcePlaneResolution）。

### 2.2 部署 overlay（不提交、链运行专用 `--patch` 文件）

机器特定值只进 overlay（隔离目录），不进 shipped 文件：

- `webserver` 端口改链专用（避开 3080/3081/3082）。
- `shadow-router` 行替换 config：`authorizedRoots`=[链工作树根+第二项目根]、`shadowSessionId`=<boot1 观测到的主会话 id>（二相引导：boot1 不配或占位→观测 id→写 overlay→boot2 生效；markShadow 幂等，config 面即已并入的宿主接入路径 eb44be73f6）。
- `project-memory` 行替换 config：`vaultRoot`=隔离 Vault 目录、`writeEnabled: true`（userScopeEnabled 保持 false）。
- 隔离 `DSH_HOME/settings.yaml`：llm-pi-ai providers huoshan-1/huoshan-2（apiKeyEnv 引用名，同宿主 settings 形状）+ `agent-default-model`（huoshan-1/glm-5.3-flash，总控/组长默认车道；Worker 由 workflow 脚本内显式 provider/model 覆盖到 huoshan-2）。
- 隔离 `DSH_HOME/.credentials.yaml`：仅复制凭据引用（不输出、不提交、不进日志）。

### 2.3 patch 语义注意（读取自 shipped 文件头与 bundle 注释）

patch 替换目标行**整个 config**（不合并）；行序无加载语义（activation 服务可用性驱动）；`!!js` 允许域=plugin config 与 entry disabled。

## 3. 真实全链设计（隔离 DSH_HOME + 隔离启动目录；每站收证）

| 站 | 动作 | 真实证据 |
| --- | --- | --- |
| S0 隔离准备 | temp DSH_HOME（settings.yaml+.credentials.yaml）+ 链工作树（git worktree，独立分支）+ 隔离 Vault + 第二项目根 | 目录清单+settings 形状（凭据值脱敏） |
| S1 启动项目 | 源启动 `dsh --profile web --patch shipped --patch overlay`（tsx），隔离 env | 启动日志、端口监听、`--dump-config` 装配探针（v14 行在列） |
| S2 总控 | 托管浏览器打开 web UI，建会话，发真实任务；主会话=总控 | 会话日志含真实 request/response（provider=huoshan-1，model=glm-5.3-flash，responseId） |
| S3 /devframe-start | 总控发 `/devframe-start <objective>`（绑定链工作树） | 成功文本 + 会话日志 devframe/role-policy、devframe/goal-binding、devframe/verification（真实子进程门执行）事件 |
| S4 组长 | 总控经 subagent（spawn）派组长 | 子会话 JSONL：真实请求 huoshan-1 |
| S5 Worker（真实 huoshan 调用） | 组长经 workflow 工具，脚本内 `agent(prompt,{provider:'huoshan-2',model:'glm-5.3-flash'})` 显式车道 | Worker 会话 JSONL：request/header provider=huoshan-2 + model=glm-5.3-flash + 响应帧；产出文件落链工作树 |
| S6 产出+独立审查 | Worker 交付落盘；fork/独立 subagent 审查产出 | 产出 diff + 审查会话真实请求/响应与结论 |
| S7 合并 | 组长在工作树 git merge Worker 提交（--no-verify+替代验证收据：diff --check+尾随换行自查） | merge 提交 SHA + 验证收据 |
| S8 停止 | SIGTERM 停止 dsh 进程 | 干净退出证据（dispose 日志尾） |
| S9 重启 | 同隔离 home 重启；重开同一会话（持久化恢复） | 会话列表含原会话；projection 重建 |
| S10 /devframe-resume | 同会话发 `/devframe-resume` | 成功文本 + 新 devframe/goal-binding 事件（revision+1）+ store 重绑 |
| S11 B2 Shadow 站（boot2） | 总控（overlay 已声明 shadowSessionId）用 project_open/project_send/status 对第二项目根真实投递；隔离验证 | KV 域 bindings/deliveries 表行 + received≠completed + 单项目 stop 隔离证据 |
| S12 B3 Memory 站（boot1+boot2） | 真实 memory_append 写 Vault→读回；重启后冷恢复读+回执重水化 | Vault 恰 N 真实 .md + 会话日志回执事件 + boot2 读回一致 |

真实调用纪律：本链内真实调用仅限链任务；每站记录实际请求 provider/model（会话 JSONL request/header 为准，标签≠成功）；429/超时按账号健康记录并切换（切换须记录）；禁盲重试。

## 4. B4 设计（S1 真实凭据重测，huoshan 显式路由）

勘误基线：原失败=deepseek-official 缺凭据（MISSING_CREDENTIAL，llm-deepseek 路由），非 huoshan 失败。改测：隔离 profile + 隔离 settings.yaml（huoshan 路由）+ 凭据引用进隔离配置，agent-default-model 指 huoshan 路由，重跑同任务（reply with the single word ok）。预期翻转为真实 PASS：exit 0、stdout='ok'、恰 1 会话目录、会话日志含真实 request/response（provider/model 实录）。harness 变体脚本落本树 `.agents/devframe/v14-udeliver/harness/`（参照 v14-accept s1-headless-run.mjs 改造），执行由组长亲跑。

## 5. B5 对账方法（36 条）

判定基准=本树 @6b31951491（=main@908f627101+已并波）。四分片：AT1×11（已完成 Worker 片）、AT2×8、AT3×9、AT4×8（后续 Worker 片）。每行：覆盖/链接/缺口/小切片。硬规则：机制 B（进程内）证据不充当全范围验收；keyless 不充当真实任务效用；同提交同环境同命令通过结果复用不重跑；S2-S7 通过不提升为全范围验收。AT1 组速览（Worker at1-recon）：覆盖 5 / 部分 4 / 缺口 2（AT1-08 repairLimit 零实现；AT1-11 真实任务效用零证据——B4/B1 链直接推进）。

## 6. 车道与结算

- B 线 Worker 显式 `{provider:'huoshan-2', model:'glm-5.3-flash'}`（总控 2026-09-06 车道修正）；每 Worker 结算登记：派发参数+实际请求 provider/model（以持久化会话 JSON 为准可得则录，不可得如实记）+结果。
- 门禁：verify-cordis-config、build/typecheck（涉 manifest/paths）、diff --check、单尾随换行、test:docs（涉 docs 时）。宿主无 bash：commit --no-verify + 等效验证收据。
- 禁区：packages/sdk/**、vendor/**、其他线域、主树写、用户 376 脏文件。
