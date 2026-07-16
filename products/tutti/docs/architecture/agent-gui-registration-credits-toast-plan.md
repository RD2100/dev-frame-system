# AgentGUI 新用户注册积分到账提示规划

## 背景

Tutti 桌面端已有账号登录链路和账号菜单：

- daemon 通过本地 `auth.json` 读取 `session_id`。
- daemon 通过 Tutti Commerce gateway 聚合会员和积分信息。
- AgentGUI 左下角账号区展示用户、会员档位和积分余额入口。

`tsh-commerce` 已提供积分领取接口：

- `POST /v1/credits/login-claim`
- 当前接口返回 `first_login_claimed`、`first_login_grant_no`、`first_login_grant_credits`、`daily_claimed`、`daily_grant_credits`、`available_credits` 等字段。

产品语义需要收敛为“新用户注册积分到账”，不是每日积分、签到、成长计划或活动卡。

## 目标

1. 新用户注册奖励到账后，给用户一个轻量、明确、可忽略的反馈。
2. 不打断当前 AgentGUI 会话，不强制切换 provider。
3. 不暴露 `session_id` 或 cookie 给 renderer/AgentGUI package。
4. 同一笔注册奖励只曝光一次。
5. 积分余额继续由账号区或账号菜单承载，不在 toast 内承载复杂导航。

## 非目标

- 不实现每日积分领取入口。
- 不做长期活动卡、成长计划卡或任务面板。
- 不在 toast 中提供 `查看积分` 按钮。
- 不因为奖励到账自动切换到 `tutti-agent`。
- 不让 renderer 直接请求 Commerce。

## 产品体验

### 展示位置

toast 展示在 AgentGUI 左侧 conversation/sidebar 底部账号区上方。

要求：

- 普通浮层 toast，不带箭头、尾巴、气泡指针。
- 与账号 row 对齐，宽度接近账号 row。
- 不遮挡主会话内容。
- 自动消失，且用户可手动关闭。

### 文案

推荐文案：

```text
新用户积分已到账
+500 通用积分
已加入你的账户余额
```

说明：

- `500` 使用后端返回的 `first_login_grant_credits`。
- 如果后端配置变化，UI 不写死积分数。
- 不出现“每日”“明天再领”“成长计划”等语义。

### 行为

- `first_login_claimed=true` 且 `first_login_grant_credits>0` 时展示。
- `daily_claimed=true` 不触发该 toast。
- toast 5 到 7 秒自动消失。
- 右上角关闭按钮立即关闭。
- 点击 toast 本体不执行动作。

## 状态模型

daemon 或 desktop service 需要维护两个概念：

```text
pendingRegistrationCreditsToast:
  userId
  grantNo
  credits
  createdAt

shownRegistrationCreditsToast:
  userId
  grantNo
  shownAt
```

推荐 key：

```text
registrationCreditsToastShown:{userId}:{firstLoginGrantNo}
```

规则：

- `grantNo` 优先使用 `first_login_grant_no`。
- 只有展示成功后才写 `shown`。
- 如果 AgentGUI 未打开或账号区未挂载，保留 pending。
- 下次 AgentGUI 账号区可见时展示 pending toast。
- 如果用户退出登录，清空当前内存 pending；已写入的 shown 标记保留。

## 数据流

### 登录完成 / 账号区刷新

1. 用户在 Tutti 账号体系中完成登录/注册。
2. desktop 登录完成后刷新 user info 和 `product_summary`。
3. daemon 在首次已登录 `product_summary` 刷新时读取本地 `auth.json`。
4. daemon 使用本地 session cookie 调 Commerce：

```http
POST {TUTTI_COMMERCE_BASE_URL}/v1/credits/login-claim
Cookie: session_id=<session>
Content-Type: application/json

{}
```

4. 如果返回首次注册奖励：

```json
{
  "first_login_claimed": true,
  "first_login_grant_no": "his_xxx",
  "first_login_grant_credits": 500,
  "available_credits": 500
}
```

5. daemon 只消费首次注册奖励字段，并把当前用户记为 attempted，避免现有 `login-claim` 的 daily grant 逻辑在后续账号区刷新中反复触发。
6. 如果返回首次注册奖励，daemon 生成 pending toast event。
7. daemon 随后刷新 Commerce membership/credits overview，使同一次 `product_summary` 尽量拿到 claim 后的余额。

### AgentGUI 展示

1. Desktop host 从 account service 读取 pending reward event。
2. 将事件映射成 AgentGUI `accountMenuState` 或独立 `accountToastState`。
3. AgentGUI 账号区挂载后展示 toast。
4. toast 关闭或自动消失后，host 回调确认展示完成。
5. service 写入 shown 标记并清除 pending。

## 接口与职责边界

### daemon

职责：

- 读取本地 session。
- 调用 Commerce `login-claim`。
- 解析首次注册奖励字段。
- 不把 cookie/session 泄露给 renderer。
- 提供 pending reward event 给 desktop renderer。

建议新增或扩展 account service 方法：

```go
type RegistrationCreditsReward struct {
  UserID    string
  GrantNo   string
  Credits   int64
  CreatedAt time.Time
}
```

可选 API：

- 在 `GET /v1/account/product_summary` 中附带一个可选 `registration_credits_reward` 字段。
- 新增 `POST /v1/account/registration_credits_reward/dismiss`，由 renderer 在 toast 关闭或自动消失后回调 daemon 写 shown 标记。
- 或新增独立只读接口 `GET /v1/account/reward_events`。

落地：先附加到 `product_summary`，因为账号区已经依赖它刷新；另加 dismiss endpoint 只用于确认曝光，不承载领取动作。

本地状态文件：

```text
<account auth.json 同目录>/registration-credits-reward.json
```

状态内容包含：

- `pending`：尚未确认曝光的注册奖励。
- `shown`：已曝光/关闭过的 reward id。
- `attempted`：已对该用户执行过 `login-claim` 的时间戳，降低 current Commerce daily side effect 风险。

### desktop renderer

职责：

- 保留 product summary 缓存和 pending reward event。
- 登录完成后刷新 user info 和 product summary；claim 由 daemon 在 product summary 内部完成。
- AgentGUI 可见时把 toast state 注入 AgentGUI。
- 展示完成后通知 service 写 shown 标记。

### AgentGUI package

职责：

- 只渲染 host 注入的 toast state。
- 不请求网络。
- 不持有 cookie/session。
- 不理解 Commerce 原始字段。
- 所有用户可见文案走 AgentGUI i18n。

建议 props：

```ts
interface AgentGUIAccountRewardToastState {
  id: string;
  title: string;
  creditsLabel: string;
  description: string;
  visible: boolean;
  autoDismissMs: number;
  onDismiss(): void;
}
```

## `tsh-commerce` 语义风险

当前 `POST /v1/credits/login-claim` 同时包含首次登录奖励和每日登录奖励语义。

当前代码没有可用开关可以关闭每日积分发放：

- `credits.daily_grant_credits` 只是额度配置，不是启停开关。
- `daily_grant_credits <= 0` 会回退到默认值，因此把配置设为 `0` 不能禁用 daily grant。
- `LoginClaim` 会固定尝试首次登录奖励和每日奖励两段逻辑。

Tutti 第一阶段处理：

- 仍调用该接口。
- 只使用 `first_login_claimed`、`first_login_grant_no`、`first_login_grant_credits`。
- 忽略 `daily_claimed` 和 `daily_grant_credits`。

后续建议：

- 在 `tsh-commerce` 拆出注册奖励接口，例如 `POST /v1/credits/registration-claim`。
- 或增加显式配置关闭 daily grant，例如：

```yaml
credits:
  first_login_grant_credits: 500
  daily_grant_enabled: false
  daily_grant_credits: 200
```

- 避免一个接口同时表达“注册奖励”和“每日签到”。

## 失败策略

- `login-claim` 网络失败：不阻塞登录完成，不展示 toast；下次账号区刷新可重试。
- `login-claim` 返回 401/403：视为 session/auth contract 问题，账号服务按现有登录失效处理。
- 返回 `first_login_claimed=false`：不展示 toast。
- toast 展示失败或组件未挂载：保留 pending，等待下一次 AgentGUI 可见。

## 测试计划

### daemon

- 登录完成后使用 `Cookie: session_id=...` 调 Commerce `login-claim`。
- `first_login_claimed=true` 时生成 pending reward event。
- `daily_claimed=true` 但 `first_login_claimed=false` 时不生成注册 toast。
- 同一 `userId + firstLoginGrantNo` 已 shown 后不重复生成。
- Commerce 失败不阻塞登录和 product summary。

### desktop renderer

- 登录完成后触发注册积分 claim，再刷新 product summary。
- pending reward 在 AgentGUI 账号区可见时展示。
- 自动消失和手动关闭都会写 shown。
- 登出清空当前 pending。
- stale 登录请求返回不会污染新账号状态。

### AgentGUI

- toast 渲染在账号 row 上方。
- toast 不带箭头、不带 CTA。
- toast 文案走 i18n。
- 自动消失计时可测试。
- 关闭按钮可关闭。

## 实施顺序

1. 在 daemon account service 增加 registration credits claim 调用。
2. 增加 pending/shown reward event 状态和测试。
3. 扩展 account product summary 或新增 account reward event API。
4. 更新 generated client。
5. 扩展 desktop account service，把 reward event 注入 AgentGUI host props。
6. 在 AgentGUI account footer 上方实现无 CTA toast。
7. 增加 i18n key 和测试。
8. 跑 targeted checks。

建议验证命令：

```sh
pnpm check:i18n
pnpm --filter @tutti-os/agent-gui test
pnpm --filter @tutti-os/desktop typecheck
cd services/tuttid && go test ./...
```

## 决策摘要

- 这是新用户注册积分到账提示，不是每日积分。
- toast 只反馈到账，不承载操作。
- 不要 `查看积分` 按钮。
- 不要箭头。
- 不自动切到 Tutti Agent。
- 使用 `user_id + first_login_grant_no` 防重复曝光。
- daemon 继续持有 Commerce 调用权限，AgentGUI 只消费 host 注入状态。
