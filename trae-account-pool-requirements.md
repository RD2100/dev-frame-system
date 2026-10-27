# Trae 账号号池与自动切换 — 需求与设计记录

- **创建日期**: 2026-10-06
- **状态**: 需求已确认,未开工(路线选择:暂不打补丁,后续基于上游开源插件自行改造并开源)
- **基线**: 调查结论全部来自 `dsh-connect-trae` **2.7.0** 源码实测(本机安装于 `C:\Users\25313\.dsh\profiles\desktop\node_modules\dsh-connect-trae\`)
- **上游**: <https://github.com/dingminhua/dsh-connect-trae> · License **MIT**(Copyright (c) 2026 LaoDing)→ 可 fork,须保留原版权声明
- **源码锚点约定**: 下文 `index.js:L行号` 均指 `lib/index.js`(5065 行,2026-10-06 版本);行号会随上游演进漂移,以符号名为准

---

## 1. 背景与目标

dsh-connect-trae 让 DSH 直接复用本机已登录 Trae 的账号调用 Trae 官方模型网关(消耗 Trae 账号自身套餐额度)。当前它只支持**多账号发现 + 每区域手动切换单账号**;我们希望升级为**订阅管理式的号池**:

> 多个 Trae 账号组成号池,请求失败(额度耗尽 / 401 / 限流)时**自动切换**到下一个可用账号,对 DSH 透明供数。

**目标**
1. 号池 = 本机各版本登录态 + 外部导入的账号文件(两者合并、统一轮换)
2. 失败自动换号,策略可配置(默认 sticky + failover)
3. 号池可视化:每账号额度 / 状态 / 冷却 / 最后使用时间(插件设置卡片内)
4. token 自动续期(复用上游刷新协议),安全边界不降级

**非目标**
- 不重写 Trae 私有聊天协议(直接复用上游请求链,不做独立代理)
- 不做跨机分布式号池(外部账号以文件导入,单机使用)

## 2. 术语

| 术语 | 含义 |
|---|---|
| 凭证 (credential) | 一份 accessToken(+可选 refreshToken/过期时间/userId),来自一个 Trae 账号在一个客户端里的登录态 |
| 区域 (region) | `cn`(国内网关)/ `ai`(国际网关);凭证归属区域由 token 来源主机名判定 |
| 版本 (edition) | Trae 桌面/CLI 的发行变体:`cn` / `sg` / `solo` / `solo-sg` |
| 号池 (pool) | 同区域内全部可用凭证的有序集合 + 轮换状态机 |

## 3. 上游 2.7.0 现状

### 3.1 已有能力(直接继承)

| 能力 | 实现位置 |
|---|---|
| 多版本凭证扫描(4 个桌面版 + CLI 兜底) | `traeStorageCandidates()` index.js:L886-917;`APP_NAMES` L816-821;CLI 兜底 `~/.trae-cn/trae-jwt-token` L828-830、`traeCliCandidates()` L929-944 |
| 按账号去重合并 | `TraeCredentialStore.readDesktopAll()` L1313-1334(`traeAccountId` 去重) |
| 插件自有凭证副本 + 按区域隔离 | `~/.dsh/.trae-auth.json` / `.trae-auth.cn.json` / `.trae-auth.ai.json`;`TRAE_AUTH_FILENAME` L1009、`TRAE_OWN_PREFIX` L1011;登出只删自己的副本 |
| 每区域账号选择(手动) | Config `accounts: {cn, ai}` L4660-4663;`select()` L1197-1199(accountId 命中则用之,否则 `preferred(credentials)` = 首个) |
| token 自动续期 | `refreshNow()` L1347-1377;临期 5 分钟提前刷新(`refreshMarginMs = 3e5` L1112);刷新失败且已过期 → 报 "sign in again in Trae" |
| 错误分类(**做轮换的关键地基**) | `result.kind ∈ authentication(401/403) \| hard_credit \| soft_rate \| client \| transport…`,见 L3163、L3275-3300 |
| 官方网关与协议 | `REGION_GATEWAYS` L954-963(见 §5.3);`Authorization: Cloud-IDE-JWT <token>` L1876/L2890;聊天 `/api/ide/v2/llm_raw_chat` L4837;SOLO 聊天 `TRAE_SOLO_CHAT_PATH` L2223 |
| 设备指纹(真实安装派生,非随机伪造) | `identityHeaders()` L1627-1643;`telemetry.machineId` / `telemetry.devDeviceId` L1470-1471;product.json 版本 L1496 |
| 回环专用管理端点(可扩展模式) | 模型刷新 `/plugins/dsh-connect-trae/models/refresh` L3879、账号重扫 `TRAE_ACCOUNTS_REFRESH_PATH` L3888、签到 `TRAE_CHECKIN_PATH`(仅 loopback) |
| 日志脱敏 | 错误消息中 JWT 替换为 `[redacted token]` L4041 |

### 3.2 缺口(即本项目要补的)

1. **无自动轮换**:全代码无 rotate / failover / pool / roundRobin 逻辑(关键词全量检索 0 命中);请求失败直接上抛,不换号。
2. **无法注入外部凭证**:凭证只能来自本机扫描;Config 只有 `authFile`(单一 storage.json 路径覆盖,L4665),不能追加多份。
3. **无号池状态展示**:卡片只有当前选中账号的用量概览。

> **重要情报(2026-10-06 核实)**:同作者(dingminhua)的 **dsh-connect-workbuddy 3.6.0 已经内置完整号池**:README 明确「把要用的账号勾进池子 → 一键签到所有账号、一键测试所有账号 × 指定模型;开启『启用账号池』即同时打开**自动换号**——请求在上游失败时依次用池内其他可用账号重试,直到有一个接手或全部不可用」。trae 上游最新版即 2.7.0(releases 检索至 2026-10-06),尚无此功能。**P1 的最优路径 = 把 workbuddy 的账号池实现移植到 trae fork**(同作者、同架构、同回环端点模式,移植成本远低于从零写)。

## 4. 需求详述

### R1 号池构成(本机登录态 + 外部导入合并)

- **本机源**:维持上游扫描链(4 版本 storage.json + CLI token)。
- **外部源**:新增号池目录 `~/.dsh/trae-pool/`,**每个文件 = 一份原样 Trae `storage.json`**(不做私有格式,`parseTraeStorageDocument()` L1549 区段可原样解析,保持与上游兼容;文件名建议 `<account-别名>.storage.json`)。
- 合并去重键:`traeAccountId`(上游现有函数);外部文件与本机登录态撞号时,本机优先(它有活刷新源)。
- 号池目录在每次账号重扫(现有 `TRAE_ACCOUNTS_REFRESH_PATH` 端点)时重新枚举;文件删除 = 账号出池。
- 外部文件里的 token 过期后走同一套刷新协议续期,刷新结果写回插件自有副本区(按区域文件),**不回写用户的原始文件**。

### R2 自动切换策略(错误驱动)

触发条件(复用上游错误分类,无需自行判 HTTP 码):
| kind | 含义 | 动作 |
|---|---|---|
| `authentication` | 401/403 | 先对该凭证强制刷新一次;刷新后重试原请求一次;再失败 → 标记冷却并切下一账号重试 |
| `hard_credit` | 额度耗尽 | 该账号冷却到"下次签到后"(简化:冷却至当地次日 00:05);立即切下一账号重试 |
| `soft_rate` | 限流 | 该账号短冷却(默认 60s,可配);切下一账号重试 |
| transport / 5xx | 网络/服务端 | 指数退避重试当前账号(≤2 次),不切号(避免把网络抖动误判为账号问题) |

- 每次换号重试整条请求链,**同一次用户请求最多换 N 个账号**(N = 池大小,上限建议 5),全池失败才向用户报错(错误消息汇总各账号失败原因,沿用脱敏)。
- 切换成功后进入 sticky:后续请求粘住新账号,直到它再触发切换条件(不做每请求轮询,保持会话侧行为稳定)。
- 冷却中的账号不参与选择;冷却期满自动回池。
- 手动选中的账号(`accounts.{cn,ai}`)语义升级为"首选",不再是排他指定:首选可用就用首选,不可用才轮换。

### R3 策略配置(Config 扩展)

```jsonc
// 建议的 Config 新增(全部 volatile,卡片可改)
"pool": {
  "mode": "sticky" | "failover" | "round-robin",   // 默认 sticky(= sticky + R2 failover)
  "cooldownSoftRateSeconds": 60,
  "maxSwitchesPerRequest": 5,
  "enabled": true
}
```
- `round-robin`:每请求取池内下一个(适合把各账号额度均衡消耗)。
- 区域粒度:cn / ai 各自独立池、独立策略(上游本就按区域隔离)。

### R4 状态与 UI

- 设置卡片每区域 tab 内新增「号池」列表:账号别名(来自外部文件名 / 本机账号标识)、区域、状态(可用/冷却中[剩余时间]/额度耗尽[恢复时间]/刷新失败)、剩余额度(复用现有用量端点,见 §5.4)、最后使用时间。
- 展示数据由插件宿主侧内存态 + 新增一个只读回环端点(如 `/plugins/dsh-connect-trae/pool/status`)供浏览器半侧拉取——沿用上游回环端点注册模式(L4249-4256)。

### R5 安全与合规(不降级)

- token 永不出本机:仅与 Trae 官方域名通信(域名单 §5.3);日志沿用 `[redacted token]` 脱敏。
- `~/.dsh/trae-pool/` 下文件含长效凭证:文档必须提示用户自行保管;建议插件对该目录读写时保持用户文件原样(只读导入,不移动不删改源文件)。
- 号池文件不做云同步、不上传。

## 5. 实现情报(源码调查所得,开工前速查)

### 5.1 凭证文件格式

- Trae 桌面登录态:`%APPDATA%\<版本名>\User\globalStorage\storage.json`,关键键 **`TRAE_AUTH_STORAGE_KEY = "iCubeAuthInfo://icube.cloudide"`**(L456),值是字符串:明文 JSON 或加密串(`parseTraeAuthValue()` L761 自动判别,加密走 `decryptTraeStorageValue()`)。
- CLI 兜底:`~/.trae-cn/trae-jwt-token`,裸 JWT 或 `{token|accessToken|jwt}` 信封(L785-813);仅 CN 区受支持(L1301)。
- 插件自有副本:`~/.dsh/.trae-auth{,.cn,.ai}.json`,字段含 `token / accessToken / userId / expiresAtMs / refreshExpiresAtMs / refreshToken`(L1047-1086)。

### 5.2 刷新协议(可直接复用)

- `REFRESH_CONTRACT`(L1382-1400):clientId **CN/SOLO = `ono9krqynydwx5`**,国际 = `en1oxy7wnw8j9n`。
- `refreshTraeCredential()`(L1415-1449):POST 刷新端点,请求体含 `ClientID / RefreshToken`,响应取 `accessToken / RefreshToken / 过期时间`;HTTP 非 200 或无 token 即失败。
- 请求设备身份:`refreshDeviceSafe()`(L4790-4805)→ `refreshTraeCredential(credential, signal, device)`。

### 5.3 网关与协议端点(REGION_GATEWAYS,L954-963)

| 区域 | chat | remote(模型目录) | pay(用量/签到) |
|---|---|---|---|
| cn | `https://trae-api-cn.mchost.guru` | `https://solo.trae.cn/api/remote/v1` | `https://api.trae.cn` |
| ai | `https://coresg-normal.trae.ai` | 同 chat 主机 `/api/remote/v1` | `https://growsg-normal.trae.ai` |

- 聊天:`POST {chat}/api/ide/v2/llm_raw_chat`(L4837),鉴权头 `Cloud-IDE-JWT <token>`;SOLO 通道另有 `TRAE_SOLO_CHAT_PATH`(L2223)。
- 区域判定:`regionOfCredential` —— 主机名 `.trae.ai` → ai;`.trae.cn` / `.trae.com.cn` → cn(L982-994)。
- Work-credit 用量端点 **CN 专属**,国际区不存在(L3779 注释)→ 国际账号的额度展示要降级处理。

### 5.4 轮换需要挂接的接缝

- 取凭证:`TraeCredentialStore.select()`(L1197-1199)与聊天客户端的 `this.options.credential()`(如 L3712、chatStream 内)。建议在 **store 层**实现轮换状态机(select 返回"当前可用凭证"),而非在每条聊天路径散改。
- 失败分类出口:L3163(分类归一)与 L3275-3300(shouldRetry 语义)——轮换决策就挂在这两类返回之后。
- 账号切换的既有写入通道:`accounts` Config 字段(L4660-4663,volatile),轮换状态机应绕开它另存运行时状态(内存态即可,不必持久化冷却表;重启即重置可接受)。

### 5.5 本机已核实环境(2026-10-06)

- Trae CN 与 TRAE SOLO CN 均已登录(`%APPDATA%\Trae CN\...\storage.json` 21988B、`%APPDATA%\TRAE SOLO CN\...\storage.json` 11529B)→ 本机池天然 ≥2 账号。
- 插件经市场安装,登记于 `C:\Users\25313\.dsh\profiles\desktop\package.json`(依赖 L13 + bundles L45)。

## 6. 实施路线

| 阶段 | 内容 | 交付物 |
|---|---|---|
| **P0 PoC(可选)** | 直接 patch 本机 `lib/index.js`:select 层加冷却 + 失败换号(仅本机账号,~60-80 行),验证策略手感 | 补丁 + 一键重放脚本(插件升级会覆盖,重放即恢复) |
| **P1 正式 fork** | fork 上游 → **优先移植 workbuddy 3.6.0 的账号池实现**(自动换号/批量签到/池状态) → R1 号池目录 + R2 轮换状态机 + R3 Config 扩展;补测试(上游带 fixtures 测试文化,L4549 注释可证) | 可发布的 fork 版本 |
| **P2 UI 与聚合** | R4 号池状态卡片 + 用量聚合(多账号用量一屏);国际区额度降级展示 | 完整「订阅管理」体验 |
| **P3 开源发布** | 独立包名发布(避免与上游混淆,如 `dsh-connect-trae-pool`);MIT + 保留 LaoDing 版权声明;向上游提 PR 回馈轮换核心 | 开源仓库 |

## 7. 风险与开放问题

- **[合规] Trae 服务条款**:多账号池化使用可能触碰 Trae ToS 对单用户/多账号的限制,开源发布前需自查条款表述,文档加免责声明。
- **[脆弱性] 私有协议漂移**:clientId、网关、wire 格式均为逆向核实所得(上游注释多处标注 verified 日期,如 2026-09-15/09-26),Trae 改版即失效;跟随上游更新是主要维护成本。
- **[稳定性] 去重键**:`traeAccountId` 的构成(userId?host?)需在 P1 时精读;外部导入的同一账号在不同机器的 storage.json 里 accountId 是否一致待验证。
- **[体验] 冷却表不持久化**:DSH 重启后冷却清零,首轮可能连环撞 `hard_credit`;可接受(P1 再评估是否落盘)。
- **[已知边界] 国际区无用量明细端点**(L3779):R4 对 ai 区账号只展示状态不展示额度明细。
- **Open**:签到自动化是否纳入(上游已有每设备每日一次的签到端点;池化后"每账号签到"是额度最大化的关键,建议 P2 做)。

## 8. 附:本次调查中确诊并修复的宿主环境问题(教训存档)

2026-10-05 trae 插件「装了但不出现」的根因:profile `node_modules` 里残留 3 个被 pnpm-lock 遗弃的旧版包(10-02 批次:`@deepseek-ai/dsh-llm-pi-ai@0.1.0-rc.6`、`@deepseek-ai/dsh-llm@0.1.0-rc.6`、`@earendil-works/pi-ai@0.82.1`),在 hoisted 布局下**遮蔽宿主 app 自带新版**,导致插件 peer-import 命中旧副本后 `SyntaxError: ... does not provide an export named 'deepEqualJson'`,加载器静默跳过整个 bundle。已改名隔离至 `node_modules\.orphan-quarantine-20261006\`。

**对 P1 的启示**:fork 开发调试时插件就装在 profile 的 hoisted node_modules 里,新增依赖若与宿主 app 版本漂移会复现同类遮蔽;发布物必须 pin 与宿主兼容的 peer 范围(>=0.1.7-rc.1 <0.3.0-0),排查「插件凭空消失」先看 `%APPDATA%\DSH Desktop\logs\host\*.log`(真宿主日志),不是 Electron 主日志。
