# Agent Note: 稳定的 profile 身份与源码检出的 DevFrame 模板

Status: implemented

[English](2026-09-04-profile-identity-and-devframe-template.md) | 中文

## 问题

Profile 组合需要一个持久身份，供启动器和 profile 感知插件使用；格式错误的 manifest 与越出 bundle 根目录的 patch 也必须在 Cordis 挂载 profile 前失败。DevFrame 仍是实验性功能，应通过现有 profile 启动链路组合，而不是增加另一个应用入口。

## 决策

在 profile package manifest 中以 UUID v4 品牌类型 `ProfileId` 保存 `dsh.profile.id`。`ensureProfileIdentity()` 在现有 manifest 锁内创建它，在多次启动之间保留该值，并将它与配置的 profile 名称一并返回。CLI 在启动挂载 profile 前提供该身份。Manifest 读取器校验自有对象字段的类型、bundle 数组、重复名称、reload 模式、profile ID 和 bundle patch 路径；patch 必须是 bundle package 目录内的相对且已存在文件。`devframe` 模板显式组合 `@deepseek-ai/dsh-base`、`@deepseek-ai/dsh-headless` 与私有的 `@deepseek-ai/dsh-experimental-agent-team-profile` 层，并使用 startup patch reload。

## 曾考虑的替代方案

- **由 profile 名称或目录派生身份。** 重命名或复制 profile 会改变身份，而且无法区分配置名称相同的两个 profile。
- **增加专用 DevFrame CLI 二进制。** 这会重复受支持的 profile 启动器，并让实验性组合看起来像独立的应用入口。
- **扫描 package metadata 自动发现 bundle。** 隐式图发现会隐藏组合顺序，也让加载时更难拒绝格式错误或非预期的 package 引用。

## 后果

- 多个进程首次并发启动时会收敛到同一个持久 profile 身份，后续启动可以使用同一身份关联工作。
- `devframe` 仅作为源码检出 profile 提供；发布 bundle 不能静默引入私有的实验性 Agent Teams 层。
- Profile 和 bundle metadata 错误会在应用启动前报告，调用方必须将 patch 文件保留在声明的 package 根目录内。
- 该身份属于 profile 启动数据；它不改变会话持久化，也不定义 DevFrame controller、worker 或 reviewer 的运行时策略。
