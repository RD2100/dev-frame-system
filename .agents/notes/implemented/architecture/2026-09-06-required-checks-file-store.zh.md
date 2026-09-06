# Agent Note：文件后备的必需检查存储

Status: implemented

[English](2026-09-06-required-checks-file-store.md) | 中文

## 问题

必需检查准入谓词消费 `RequiredChecksConfigStore`，但此前唯一实现是进程内存：每次重启都会把检查源清空，P05 登记的 durable 覆盖规则因此没有持久承载，重启后的宿主对上一个进程登记过的证据只能回答 `REQUIRED_CHECKS_CONFIG_NOT_FOUND`。[完成准入 seam](2026-09-06-goal-completion-admission-seam.zh.md) 在锚定证据完整性的那个谓词上始终存在重启脆弱性。

## 决策

`FileRequiredChecksConfigStore` 在 `Config` 提供的 JSON 账本路径上实现既有接口：信封为 `{ version: 1, registrations: [{ digest, config }] }`，每次读取都会重新解码已登记载荷，并把声称的 digest 与 `requiredChecksDigest(decoded)` 比对。字节不可解析、信封不合、digest 漂移三者一律以新的稳定码 `REQUIRED_CHECKS_STORE_CORRUPT` fail-loud；`save` 面对损坏账本同样拒绝——绝不原地修复。发布经同目录临时文件加 rename；重复保存已知 digest 是幂等空操作；`sameRequiredCheckCommand`、`acceptanceCheckComponent`、`evaluateRequiredChecks` 与 digest 算法零改动。该存储仅作为可注入替代实现交付；在 profile 或组合中选用它属属主波的决策。

## 落选替代

**自动修复或截断损坏账本。** 修复会静默销毁篡改证据；以稳定码 fail-loud 让账本保持完整性面，与准入的 fail-closed 方向一致。

**同片引入 fsync 与多写者锁。** 掉电级 durability 与并发写合并会在尚无调用方需要时扩张面；单写者 last-write-wins 语义已写入存储契约，设计记录将它们列为显式裁定请求。

**现在就把存储接入 profile。** 持有它的组合已提供存储注入点；按 profile 选择 durable 实现是部署决策，不是库事实。

## 后果

- 配置了账本路径的宿主获得可跨重启的必需检查源；准入的 checks 谓词不再绑定内存。
- `REQUIRED_CHECKS_STORE_CORRUPT` 加入错误族；读到漂移或损坏账本会得到一个稳定码而非裸解析错误。
- 并发、fsync、目录创建、非 `ENOENT` IO 错误包装与账本 compaction 仍超出范围，已登记为裁定请求。
