# C4 核验：手机配对（安装面自动核验 + 真用户动作最小清单）

- 工作树：D:/dsh-devframe-v14-product-lead（分支 codex/v14-product-lead @ 6b31951491）
- 核验方式：组长亲自只读核验（遵守"禁止调查型 Worker"令，本项无 Worker 派发）；全部读取只读，未读任何密钥材料内容，未修改核验对象。

## 一、安装面核验（自动可达部分，全部只读）

Profile（`C:\Users\25313\.dsh\profiles\mobile\`）：

- package.json：`name: dsh-profile-mobile`；`dsh.profile.bundles` = `[@deepseek-ai/dsh-base, @deepseek-ai/dsh-web-app, @dsh-mobile/interaction-operations, @dsh-mobile/ui-layout-mobile]`；`patchReload: live`；profile id `62412692-849d-4783-ae35-c7570a577c55`。
- 依赖声明：两包均来自 GitHub release tgz——`https://github.com/NOirBRight/dsh-mobile/releases/download/v1.1.6/dsh-mobile-interaction-operations.tgz` 与 `.../v1.1.6/dsh-mobile-ui-layout-mobile.tgz`（release v1.1.6）。
- cordis.yml = `[]`（空根）、cordis.patch.yml = `[]`（无覆盖层）；pnpm-lock.yaml、pnpm-workspace.yaml、node_modules、.dsh-module-fallback 均在。
- 实装包：node_modules/@dsh-mobile/interaction-operations（包内 version 字段 `0.1.15`）与 @dsh-mobile/ui-layout-mobile（`0.1.0`）——包内 version 字段落后于 release tag v1.1.6（上游未同步字段），安装来源以 package.json 的 release tgz URL 与 lockfile 为准，如实记录。
- 两包定位（各自 README.md）：ui-layout-mobile = 移动端根布局（逐字实现上游 `@deepseek-ai/dsh-client-ui-layout` 的 slot 契约，替换移动 shell 内桌面 root，README.md:3-33）；interaction-operations = 移动/粗指针输入规范化 Interaction Intents（presentation-only，README.md:3-15，"owns input, popup, and surface interaction adapters only" README.md:27）。两者均不拥有配对协议。

配对持久态（`C:\Users\25313\.dsh\mobile\`）：

- daemon-keypair.json：存在（密钥材料，内容未读、不记录）。
- devices.json：顶层 keys = `[devices]`；恰 1 台设备；设备字段 = `claimantPublicKey, clientType, createdAt, id, label, lastSeenAt, revokedAt, room, tokenHash`（只记结构与字段名，不记任何值）。含义：该 Host 的配对服务已至少完成一次真实设备注册，且字段面支持吊销（revokedAt）。

## 二、配对服务归属判定（按实际接口，不预设依赖）

- 本仓库零配对源码：packages/**、apps/** 内 `devices.json|daemon-keypair|claimant` 全树零命中；本基线（6b31951491）为 main（908f627101）祖先，范围内仅 2 个 records-only 提交（W-2 WORKLIST 更新），无源码差——即最新 main 亦无配对实现。
- 写 devices.json/daemon-keypair.json 的配对守护归属生产 DSH 运行时与签名 dsh-mobile v1.1.6 APK（ui-layout-mobile README.md:50："The signed dsh-mobile v1.1.6 APK carries this layout locally"）——协议细节（room/claim/tokenHash 握手）在 APK/运行时侧，本仓库源码不可达，如实标注为不可核面。
- 与 C3 关系（按用户纠正口径）：C4 挂载面独立成 profile（mobile 四 bundle 自成组合），核验与交付互不阻塞；仅共享 leaf 插件复用关系（移动布局令 ui-sidebar/ui-conversation 等不经修改继续工作，ui-layout-mobile README.md:3）。

## 三、本仓库面（C 线写域核对）

- packages/client/** 无任何 mobile/pairing 代码与挂载行（web-app/cordis.patch.yml 六 bundle 全量核对仅上游四插件）；C4 的 client 面完全由外部 @dsh-mobile 插件承载。
- C 线写域（packages/client/** 最小修复）与 C4 无交集：本仓库不存在可修的 C4 缺陷面；无修复切片。

## 四、真用户操作最小清单（仅真用户动作）

1. 手机安装 dsh-mobile v1.1.6 APK 并打开（若尚未安装）。
2. 在手机客户端对 Host 发起配对，并在 Host 侧确认该新设备。
3. 现有已注册设备（当前 1 台）日常直接打开即用；如需吊销/移除，在 Host 侧设备管理操作。

（配对确认的具体 UI 步骤由 APK/运行时承载，本仓库无文档可引——不臆造步骤，以上为最小必要动作。）

## 五、四态结论与三层证据分列（组长汇总）

四态（对应 remaining/WORKLIST.md C4 行）：

| 态 | 结论 |
| --- | --- |
| 源码 | client 适配面=外部包（release v1.1.6，安装产物在案）；本仓库零源码；配对守护=外部运行时/APK（本仓库不可核，诚实标注） |
| profile | 已安装启用：mobile profile 四 bundle + 锁文件 + node_modules + 空 patch 层在案 |
| 运行 | 装配级在案：daemon-keypair.json + devices.json 证明配对服务已运行且 ≥1 台设备完成注册；连接活性（lastSeenAt 时效）与真实握手=需真机动作，不在自动核验面 |
| 生产验收 | 待真用户动作确认（§四 最小清单三项） |

三层证据分列（车道纪律）：

| 层 | 内容 |
| --- | --- |
| ①请求参数 | 本项无 Worker 派发（调查型 Worker 禁令），组长亲验 |
| ②宿主标签 | n/a |
| ③实际响应 | 只读读取清单：C:\Users\25313\.dsh\profiles\mobile\{package.json, cordis.yml, cordis.patch.yml}、node_modules\@dsh-mobile\*\{package.json, README.md}、C:\Users\25313\.dsh\mobile\{devices.json(仅结构), daemon-keypair.json(仅存在性)}；git 范围核对 `git log --oneline 6b31951491..908f627101`（2 个 records-only 提交） |

## 六、可自动测面与限制

- 已自动核验：安装面（清单/依赖/锁文件/实装包结构/版本字段/空 patch 层）与配对持久态结构（字段面+设备计数）。
- 自动不可测（需真手机/账号动作）：配对握手、密钥协商、推送/连接活性、APK 内 UI 步骤——列入 §四 用户清单，不在本轮伪造证据。
