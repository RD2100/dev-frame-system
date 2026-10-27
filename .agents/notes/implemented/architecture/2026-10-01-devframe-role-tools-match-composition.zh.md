# Agent Note: DevFrame 继承角色工具与已挂载提供方保持一致

Status: implemented

[English](2026-10-01-devframe-role-tools-match-composition.md) | 中文

## 问题

绑定 Agent 发布或恢复时，继承角色允许列表会对照全局工具注册表进行验证。浏览器、图像生成、外部 worker 或 project-controller 提供方未挂载时，列表中的对应名称会阻止发布，并可能中断 Desktop 启动。仅解析 profile 或只用未绑定 Agent 启动它，不会触发这一失败。

## 决策

[DevFrame profile](../../../../packages/experimental/devframe-profile/cordis.patch.yml) 只向 controller 和 lead 提供其自身提供方挂载的全局 dispatch、expert-team、memory 和 library 工具。[Desktop overlay](../../../../apps/desktop-host/config/desktop.cordis.patch.yml) 替换完整 hierarchy 配置，加入其挂载的 project-controller 工具。两者都保留空的 worker 继承允许列表和空的 lead 插件范围。

[hierarchy 策略](2026-09-05-agent-hierarchy-policy-package.zh.md) 和 `tools.restrict()` 保持严格：未知的全局配置名称会导致失败，而不是从策略中消失。Agent 局部工具属于作用域注册，不需要列入继承全局工具允许列表。额外部署提供方与对应权限一起配置。

## 考虑过的替代方案

**按运行中的注册表静默过滤未知名称。** 这会隐藏提供方遗漏和拼写错误，把已声明的能力变成不可用工具，却不报告配置错误。

**安装所有可选提供方以满足列表。** 浏览器、图像生成和外部 worker 提供方引入了默认 profile 不拥有的依赖和部署要求。仅有权限条目不等于获准安装或启用这些提供方。

## 后果

Loader 组合测试读取随包发布的 hierarchy 配置，在没有可选提供方时发布已绑定的 controller 和 lead Agent。Desktop 组合测试检查其允许列表只通过已挂载的 project-controller 工具扩展 profile 列表。权限列表变更通过发布进行测试，而不只解析 YAML；独立的策略和 Shadow 允许列表决策继续有效。
