# Agent Note：Win32 文件夹对话框不再在选择目录时杀死 worker

Status: implemented

[English](2026-10-01-win32-folder-dialog-worker-crash-on-selection.md) | 中文

## 问题

在 DSH Desktop 应用中选择文件夹时，文件夹对话框 worker 在回报结果前被杀掉：选择器报 `directory picker failed: directory picker failed: win32 folder dialog worker exited before reporting a result`。worker 能启动、能弹出对话框、也收到了选择结果，死亡发生在结果提取阶段。`packages/host/directory-picker-native/src/win32-dialog-bindings.ts` 的 `readUtf16` 用 `Buffer.from(koffi.view(address, 32768))` 翻译 `IFileOpenDialog` 的结果，而 `koffi.view` 创建的是**外部内存** ArrayBuffer。Desktop 应用的 host 与对话框 worker 都以 electron-as-node 方式运行（`DeepSeek Harness.exe`），Electron 禁止外部缓冲区：该尝试会抛出致命的 N-API 错误，JavaScript 的 `try`/`catch` 拦截不到，worker 不发任何 IPC 消息即死亡，驱动侧只能报告进程退出。

在出厂的运行时环境复现：64 字节的 `CoTaskMemAlloc` 块装着合法 UTF-16 路径，`koffi.view` 以任何长度调用都会死（32 KiB 与 34 字节都一样），而普通 Node 24.17 执行同样的调用毫无问题。缓冲区长度无关紧要——view 调用本身就是致命点。

该缺陷逃过了所有现有检查。单元测试 mock 了 koffi，假的 `view` 返回普通 ArrayBuffer，没有 mock 观察得到运行时限制；`tests/win32-dialog.spec.ts` 中的真实 win32 冒烟只打开对话框再中止关闭，取消路径永远到不了 `readUtf16`；`dsh web` host 跑普通 Node，view 调用在那里会成功。

## 决策

`readUtf16` 改用 `koffi.decode(address, 'char16_t', -1)` 读字符串：koffi 原生拷贝字符直到字符串自身的 NUL 终止符，不再存在供运行时禁止的外部缓冲区。koffi 按完整码元解码，含 U+XX00 码元（如 开，U+5F00）的路径不会丢失——截断这类路径的字节扫描连同它扫描的缓冲区一起消失了。已在出厂 electron-as-node host 上端到端验证：真实对话框、真实选择、返回真实路径。

绑定面完全移除 `view`；`tests/win32-dialog-bindings.spec.ts` 中的假 koffi 记录并对任何 `view` 调用抛错，重新引入外部缓冲区读法会在 mock 测试车道里失败，而不是在生产里静默死亡。

## 考虑过的替代方案

**用 `lstrlenW` 定长，只 view 确切长度。** 否决：在 Electron 运行时里 view 调用本身致命，与长度无关，定长不解决任何问题。

**`koffi.decode(address, 'str16')`。** 否决：`'str16'` 是字符串指针类型，decode 会把结果地址当指针解引用而杀死 worker（已验证：进程在第一个真实 `GetDisplayName` 地址上死亡）。

**把对话框迁出 electron-as-node worker，或迁出子进程。** 否决：子进程架构拥有模态阻塞与[子进程文件夹对话框笔记](../feature/2026-08-02-win32-in-process-folder-dialog.zh.md)的中止手段，只有字符串读取需要改动。

## 后果

- win32 上 Desktop 应用的文件夹选择可以完成；worker 在结果提取后存活并通过 IPC 回报路径。
- 含 U+XX00 码元的路径经原生码元解码继续可用，取代已归档的 [2026-08-23 UTF-16 截断笔记](../../archived/bug-fix/2026-08-23-win32-utf16-nul-truncation.md)的扫描机制——那份笔记中被否决的替代方案「向 COM 或 koffi 要字符串长度」正是现在的实现机制。
- 桌面运行时以打包后的 `lib/worker.cjs` 携带 worker：已安装的应用在含修复的运行时发布前一直带着致命的 worker。
- mock 绑定测试继续覆盖 COM 会话（虚表顺序、内存卫生、中止投递）；仅 win32 的冒烟继续覆盖取消路径；选择路径的运行时安全性以本文记录及修复验证中的 electron-as-node 复现为依据。
