# A4 交付：可逆独立候选 Worktree/启动目录

基点：main @ ceb4befc59。验证环境注记：**A1/A2 两场景绿均在干净隔离树复验**（用户隔离复验+组长实跑，同内容复用）；主树 collection 被 85 个用户 src/*.js 遮蔽属保护状态，非完成口径。

## 候选树

- 路径：`D:/dsh-devframe-v14-candidate`
- 创建：`git -C D:/dsh-devframe worktree add D:/dsh-devframe-v14-candidate <main-SHA>`（本例 ceb4befc59，detached）
- 回滚：`git -C D:/dsh-devframe worktree remove D:/dsh-devframe-v14-candidate --force`（产物目录随树移除，分支零残留）
- 更新到新 main：`git -C D:/dsh-devframe-v14-candidate checkout --detach <new-main-SHA>` + `pnpm install --frozen-lockfile` + `pnpm run build`

## 终验命令与退出码（基点 ceb4befc59）

| 步 | 命令 | 退出码 |
| --- | --- | --- |
| install | `pnpm install --frozen-lockfile` | 0 |
| build | `pnpm run build` | 0（220 client artifacts, 3 public values） |
| 污染门禁 | `pnpm run verify-no-source-js` | **0**（干净树；主树同命令 fail-loud 点名 85 用户文件=设计行为） |
| clean launch | `node --import tsx/esm apps/cli/src/bin.ts web --patch apps/cli/config/examples/cordis/cordis.yml --no-open`（隔离 `DSH_HOME=<cand>/.dsh-a4probe`，TSX_TSCONFIG_PATH 指候选树） | port 3081 **LISTENING=True** + token URL 签发 |

## 主工作区保护状态（只记录，不处置）

- 85 个用户未跟踪 `packages/*/src/*.js`（mtime 09-06 11:34，untracked 未 ignore，属用户 376 脏文件集）：**控制器不删除、不 gitignore**。
- `verify-no-source-js` 在主树失败=点名真实污染的 fail-loud 设计行为，直至用户处置该 85 文件；处置前，干净候选树即为 sanctioned 验证与启动路径。
- vite 扩展序（.js 先于 .ts）遮蔽机制与产生者分析见 `repro/a3-producer-mechanism.md`；污染清单见 `repro/a3-polluted-src-js-list.txt`。

## 结论

A4 关闭：可逆候选树创建→install→build→污染门禁→clean launch 全链真实退出码在案；用户功能验收可用该候选树作为可启动的本地候选版本（启动命令即上表 clean launch 行，去掉 `--no-open` 即自动开浏览器）。
