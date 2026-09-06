# B4 — S1 真实凭据重测（huoshan 显式路由）：PASS

勘误基线：v14-accept S1 的 keyless BLOCKED = deepseek-official 缺凭据（MISSING_CREDENTIAL），非 huoshan 失败。本重测在隔离 profile 用 huoshan 显式路由重跑同任务，**判定 PASS（harness exit 0，7/7 checks）**。

## 执行命令（组长亲跑，2026-09-07，workdir=D:\dsh-devframe-v14-udeliver-lead）

```
$env:TSX_TSCONFIG_PATH='D:\dsh-devframe-v14-udeliver-lead\tsconfig.json'
node --import file:///D:/dsh-devframe-v14-udeliver-lead/node_modules/tsx/dist/esm/index.mjs .agents/devframe/v14-udeliver/harness/s1-huoshan-run.mjs --tree D:\dsh-devframe-v14-udeliver-lead --out D:\dsh-udeliver-iso\out\b4 --credentials C:\Users\25313\.dsh\.credentials.yaml
```

- harness 退出码：**0（=PASS，harness 契约 0/2/3/4）**
- 隔离面：临时 `dsh-accept-s1-huoshan-*` 根（DSH_HOME/cwd 全隔离）；凭据只进隔离 `.credentials.yaml`（存在性/字节数/引用名探针，值零记录）；子进程环境无 HUOSHAN_*（解析走凭据存储）

## 逐项检查（verdict.json 7/7 pass）

| id | 期望 | 结果 |
| --- | --- | --- |
| b4-exit-code-0 | exit 0（真实回合完成） | pass |
| b4-no-missing-credential | keyless 期 MISSING_CREDENTIAL 钉面不复现 | pass |
| b4-real-model-output | stdout='ok'（真实模型答复） | pass |
| b4-one-session-dir | 恰 1 会话目录 | pass |
| b4-request-level-provider | 请求级帧含 huoshan-1/glm-5.3-flash | pass |
| b4-real-wire-response | 真实 wire 响应帧 | pass |
| b4-credential-refs-isolated | 隔离凭据双引用在、无 ambient 变量 | pass |

## 三层车道证据（只认请求级）

- ①请求参数：隔离 settings.yaml `agent-default-model: {provider: huoshan-1, model: glm-5.3-flash}`（显式路由）
- ②宿主标签：headless 系统提示自报 "powered by the glm-5.3-flash model"（会话 config，非独立证据）
- ③实际响应（**实证层**，引用日志 seq）：
  - `request/header` **seq=10**（eventIndex 10）：`data.header.config.provider="huoshan-1"`、`data.header.config.model="glm-5.3-flash"`（逐字）
  - `assistant/message` **seq=49**（eventIndex 23）：turn 1/step 1，text="ok"，真实 wire 响应
  - 原始帧：`D:\dsh-udeliver-iso\out\b4\s1-huoshan\{request-frame,response-frame,stdout,run-record,verdict-copy}.json`（隔离目录，凭据零涉及）

## 结论

huoshan 显式路由真实调用链通（路由解析→凭据引用→真实请求→真实响应）。S1 场景由 keyless BLOCKED 翻转为真实凭据 PASS；AT1-03 旅程与 AT1-11 真实任务效用的"真实调用面"由此打通（组合级旅程归 B1 链）。
