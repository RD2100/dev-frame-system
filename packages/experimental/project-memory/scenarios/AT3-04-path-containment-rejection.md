---
description: "AT3-04 recorded-session 场景草案：路径包含/穿越拒绝面——noteId 形状、workspaceId 段校验、symlink/reparse 逃逸与不支持排他创建时 append 停用而非 shell 回退（memory_read / memory_search / memory_append）。"
kind: "acceptance-scenario-draft"
---

# AT3-04 场景草案：路径包含与穿越拒绝

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-04` / `R3.2`（穿越探测、越权命名空间 id、symlink/reparse 逃逸；不支持的安全创建使 append 停用而非 shell 回退）。

## 目标

验证真实适配器上的路径拒绝面：穿越形 note id 与越权 workspace id 在形状检查即被拒（`MEMORY_INVALID_NOTE_ID` / `MEMORY_INVALID_WORKSPACE_ID`），请求面没有可携带路径的字段；Vault 子树内的 symlink/reparse 分量或越界解析一律 `MEMORY_PATH_REJECTED`，Vault 内外零越界读写；文件系统不能提供排他创建时 append 以 `MEMORY_APPEND_DISABLED` 停用，绝不回落 shell 写。

## 前提（宿主集成）

同 AT3-01 草案：三工具需宿主装配进 profile。symlink/reparse 夹具与 ENOSYS fault 由宿主装配面构造（进程自有临时目录内）；Windows 用 junction/reparse point，POSIX 用 symlink，平台语义差异按录制平台记录。`resolveMemorySpec` 在宿主边界对每个 `workspaceId` 派生 spec，非法 id 在边界即拒、服务实例不构建。

## 计划录制布局

`snapshots/session/memory-path-containment-rejection/`：`snapshot.yml`（`profile: headless`，workspace facts 记录 `workspaceId` 与平台 reparse/symlink 语义）；`session.jsonl` 含全部被拒调用事件，且无任何 shell 工具事件；`workspace.expected/` 与 Vault 断言：探测目标目录零文件、Vault 子树仅含合法夹具。

## Vault 与工作区夹具

服务实例 `workspaceId: ws-pathsafe`，`writeEnabled: true`，临时 Vault。先以一条合法 note 建立命名空间；Vault 外探测目标为临时目录 `outside-target/`（录制前后均应为空）；reparse 夹具按步骤 3–5 逐个构造并在子案后恢复。

## 剧本（replay 步骤）

1. 穿越形 id 探测（read 路径）：`memory_read` 的 `noteId` 依次为 `../../outside-target/x`、`..%2Fx`、大写 64-hex、63 位 hex → 全部 `MEMORY_INVALID_NOTE_ID`（64-hex 形状检查先于路径解析与 Vault 访问），`outside-target/` 无任何读取痕迹。
2. 越权命名空间 id 探测：宿主以 `workspaceId` 为 `..`、`ws/../x`、`ws\x`、`ws:x`、`CON`、`ws.`（尾点）、超 128 字符分别 `resolveMemorySpec` → 全部 `MEMORY_INVALID_WORKSPACE_ID`；工具请求面只有 `scope: 'project' | 'user'`，无任何可指定他人项目命名空间或路径的字段。
3. 目录分量 reparse 探测：把 `devframe-memory/projects/ws-pathsafe` 替换为指向 `outside-target/` 的 junction/symlink → `memory_search` / `memory_read` / `memory_append` 全部 `MEMORY_PATH_REJECTED`（`unexpected symlink or reparse component`），`outside-target/` 零读写。
4. note 文件 reparse 探测：恢复目录后，把既有 note 文件替换为指向外部的 junction/symlink → 对该 id 的 `memory_read` 与对其派生路径的 `memory_append` 均 `MEMORY_PATH_REJECTED`（`note file … is a symlink or reparse point`）。
5. 未建命名空间 reparse 探测：把尚不存在的 `devframe-memory/projects/escape-ws` 预置为指向外部的 junction 后以 `workspaceId: escape-ws` 追加 → `MEMORY_PATH_REJECTED`（分量遍历拒绝），外部零文件。
6. 不支持排他创建：宿主 fault 使 note create 的 `open(path, 'wx')` 返回 ENOSYS → `MEMORY_APPEND_DISABLED`（消息含 "cannot provide the required create-only operation; append is disabled"），命名空间文件数不变；同期的 `memory_search`/`memory_read` 正常返回——停用只限 append，且录制中无任何 shell/复制/改名写文件事件。

## 可观察通过标准（对应 AT3-04）

- 内外零越界读写：步骤 1–5 每次拒绝后 `outside-target/` 与 Vault 外路径零文件、零访问，拒绝码逐子案可断言。
- 拒绝发生在包含检查：`MEMORY_INVALID_NOTE_ID` / `MEMORY_INVALID_WORKSPACE_ID` / `MEMORY_PATH_REJECTED` 全部先于任何 note 内容读取或写入。
- append 停用而非回退：ENOSYS 下稳定 `MEMORY_APPEND_DISABLED`，`session.jsonl` 中无 shell/复制/改名写文件事件。

## 环境与安全

reparse/junction 夹具只指向录制期临时目录；链接与目录用后全部清理；合成内容。

## 开放问题

- Windows junction 与 POSIX symlink 在 `lstat` 上的上报差异由录制平台决定，断言绑定 `MEMORY_PATH_REJECTED` 码而非链接种类。
- `realpath` 越界分支（`ensureNamespaceDir` 的目录 realpath 检查）是 check-to-create 竞态窗口的纵深防御，正常夹具下先被分量遍历拒绝；该分支由包行为测试持有，录制不含。
