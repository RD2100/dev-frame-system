# A3 产生机制报告：85 个 packages/*/src 编译产物

状态：机制已复现钉死 + 防复发门禁落地（verify-no-source-js）。主树用户文件零触碰。

## 污染事实（只读主树核实）

- 85 个 `.js` + 85 个 `.js.map`（git untracked，repro/a3-polluted-src-js-list.txt）；磁盘另有 85 个 `.d.ts` + 85 个 `.d.ts.map`（check-ignore 确认四类均**未被 gitignore**，untracked 可见）。mtime 全部 2026-09-06 11:34:11（同一秒，单一进程一次写出）。
- 覆盖包：attachment、app-boot、cmdline、compaction、core/agent、core/scope、core/session、core/system-prompt、interaction/commands、deepseek-llm-api-extensions、llm、session-persistence(-jsonl)、session-projection、test-support/{llm-replay,loader-smoke,session-snapshot}、typert/protocol、util/{atomic-write,brand,crypto,home-paths,launch-environment,timeout,values}——即快照/回放运行图的传递闭包。
- 文件特征（样本 packages/attachment/attachment/src/index.js vs index.ts）：ESM 保留、相对导入 `.ts`→`.js` 重写、尾部 `//# sourceMappingURL=index.js.map`、4 空格缩进、JSDoc 完整保留 → tsc emit（非打包器产物）。

## 产生机制（正向复现，scratch 隔离验证）

命令：`tsc -p tsconfig.no-outdir.json`（scratch 内，TypeScript 版本同仓库）。该配置 = tsconfig.base.json 的 compilerOptions（sourceMap/declaration/declarationMap/rewriteRelativeImportExtensions/allowImportingTsExtensions/module esnext/moduleResolution bundler）+ `include: ["src"]`、**无 outDir/rootDir**。

结果：`src/index.ts`、`src/helper.ts` 旁出现 **.js + .js.map + .d.ts + .d.ts.map 四类产物**，`.js` 内相对导入被重写为 `./helper.js`，尾部带 sourceMappingURL——与主树污染文件四特征逐一吻合。

关键机制点（复现中实测）：该次编译因 scratch 缺 @types/node **以 exit 2 失败（TS2688）但产物仍然全部写出**——tsc 无 noEmitOnError 时失败编译照样污染。即：任何"继承 base 门面 emit 选项却缺 outDir"的一次性 tsc 调用（手工排查、临时脚本、agent 自由编译）都会按此机制直写 src；`composite/incremental` 只产生 tsbuildinfo，不影响落点。

## 遮蔽效应面（既有归因确认）

vite 扩展序 `.js` 先于 `.ts`，tsconfigPaths 重写到 src 后 `index.js` 遮蔽 `index.ts`——污染文件因此接管包源语义；清缓存后才揭开。

## HEAD 工具链逐项排除（file:line）

- 包级 tsconfig 全部带 outDir：如 `packages/attachment/attachment/tsconfig.json:4`（rootDir src, outDir lib/types）。
- 面 solution 带 `files: []`：`packages/api/gateway/tsconfig.json:2`——bare tsc 于其中零输入。
- 程序化 Program 一律 noEmit：`scripts/ts-project.ts:71-81`（semanticCompilerOptions 强制 noEmit/sourceMap=false 等；防线自 c67c3d9413 2026-07-14 即存在）；其全部消费者（clean/gen-doc-graphs/gen-scoped-events/verify-client-packages/verify-optional-dependency-imports）仅做语义查询。
- typert 只写 lib 产物：`packages/typert/generator/src/tsdown-plugin.ts:113-119`（typert.<face>.js/d.ts 落 <pkg>/lib）；`scripts/gen-typert.ts` 仅调 writeBundle。
- `scripts/doc-typecheck.ts:124`、`scripts/verify-export-jsdoc.ts:572` 的 createProgram 均为校验查询，无 emit 落盘路径。
- 会话日志扫描（09-05..09-08，DSH 会话目录全量，tsc 命令过滤）：仅见 `pnpm exec tsc -b <pkg>`（正规构建模式、各自 worktree、exit 0），**无主树内非 -b 形态 tsc 调用记录**——历史产生命令应发生在 DSH 会话日志之外（非托管 shell），不可恢复，但不影响机制定性与防复发。

## 防复发门禁（本分支落地）

- `scripts/no-source-js.ts`：扫描 `packages/**/src` 下 `.js`/`.js.map`（任何深度，跳过 node_modules；hand-authored `.d.ts` 与 lib/、非 src 夹具不在域内）；存在即 exit 1 并逐文件列出，提示"remove and fix the producer; never gitignore"。
- npm script：`verify-no-source-js`；接线：`scripts/run-gates.ts` 的 `ciSharedStaticGates()`（ci-static/ci-primary/ci-consumers/windows 观察面）与 `check-all` 聚合。
- 无效用例：`scripts/no-source-js.spec.ts` 6 例——干净树通过；src 内 .js/.js.map（含深层）逐个捕获；node_modules/lib/非 src 的 .js 不误报；无 packages 目录容错；main exit 0/1 两路。
- 本树实测：`pnpm run verify-no-source-js` → exit 0（干净树）；spec 组合 run-gates.spec → 86 passed，exit 0。

## 证据纪律备注

本项调查由组长第一手完成（Controller 两次指派的 Worker 实为 C 线内容/失败废弃，见 a1a2-repro.md Worker 记录节）。主树全程只读；唯一例外为一次误写 `.rg-spec.txt` 于主树根，发现后立即删除（git status 复核主树仅余用户既有脏文件）。
