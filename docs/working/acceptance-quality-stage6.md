# Stage 6 独立质量验收报告——DevFrame 插件自包含分发改造

> 验收人：独立第三方质量审核 agent（与实现者非同一 agent）。立场是挑错而非背书。
> 验收方式：只读为主，亲自运行测试与打包 dry-run 自验；未修改/还原/提交/删除任何文件，未执行 npm publish，未触碰 `D:\dsh-upstream-latest` 与 `apps/cli/package.json`。
> 验收日期：2026-09-19。仓库：`D:\dsh-devframe`。

---

## 一、总体验收结论

**通过（无必须返工项）。**

实现与详细设计 `detailed-design-self-contained-distribution.md` 一致；6 个测试文件断言真实、我亲自运行结果为 6 文件 34 用例全绿（退出码 0）；fail-loud 语义在加载期、cordis 实例化之前生效；未越界改动 `apps/cli` 与上游只读副本；P0 数据包 files 经我亲自 `npm pack --dry-run` 实证正确；实现者声称的 9 项 tsc 错误经独立甄别确为未提交工作集的 dsh-app-boot 漂移，非本任务引入。

无必须返工项。仅有 3 条遗留观察项（均非阻断，见第四节）。

---

## 二、逐项验收意见

### 1. 改动与详细设计一致 —— 通过（抽核 7 包，超出要求的 6 包）

逐字段比对实际 `package.json` 与设计 §A 目标态：

| 包（设计条目） | 核对点 | 实测 | 结论 |
| --- | --- | --- | --- |
| `packages/workflow/worktree-registry`（A.19） | version 0.1.6-alpha.1 / 无 private / publishConfig.access=public / repository / engines | 全部命中；`dsh-brand`、`schemastery` 已从 deps 移入 peer（L43–44），deps 仅剩 `zod` | 通过 |
| `vendor/logger-console`（A.20） | 版本保留 `1.0.2` / 无 private / publishConfig / repository / engines 新增 | 版本确为 1.0.2；`cosmokit`、`schemastery` 移入 peer（L39–40）；`supports-color` 仍在 deps（L43） | 通过 |
| `packages/experimental/expert-pack-paper`（A.17，P0） | files 改为 `lib/**/*.js`+`lib/types/**/*.d.ts`+`experts/**`+`skills/**`+`team.yml`+`schemas/**` | L26–32 与设计逐字段一致；无 `team*.yml` 通配 | 通过 |
| `packages/experimental/devframe-profile`（A.18） | 无 private / publishConfig / repository / engines 新增；files 与 deps 不变 | 全部命中；files 仍含 `cordis.patch.yml`，deps 13 项未动 | 通过（见观察项 O1） |
| `packages/experimental/project-contracts`（A.1） | 无 private / publishConfig 新增 / repository 新增 / engines 新增 | 全部命中；deps 无、peer 4 项未动 | 通过 |
| `packages/experimental/expert-team`（A.12） | schemastery 从 deps 删除、新增进 peer | deps 仅剩 dsh-llm/ajv/js-yaml/zod（L54–59），schemastery 已在 peer L71 | 通过 |
| `packages/experimental/project-controller`（A.6） | schemastery 从 deps 删除、新增进 peer | deps 仅剩 zod（L57–59），schemastery 已在 peer L75 | 通过 |

`apps/desktop-host/package.json`（§C P5）：19 行追加依赖全部在场（L27–45），**不含** `devframe-profile`、`zod`/`ajv`/`js-yaml`/`react`；`@deepseek-ai/dsh-worktree-registry` 仅 1 行（L44，未在 profile 层重复）。与 §C 逐行一致。

### 2. 测试真实覆盖（非凑数）—— 通过

打开全部 6 个新增测试文件，断言均打到设计 §E 列出的行为，无空断言/同义反复：

- `scripts/desktop-plugin-delivery/devframe-publish-preflight.spec.ts`：对 20 个对象逐包断言非 private、版本、engines、publishConfig.access=public、repository 在场、4 个框架单例不在 deps（20 个 it）。
- `scripts/desktop-plugin-delivery/expert-pack-files.spec.ts`：断言两包 files 声明含 `experts/**`/`skills/**`/`team.yml`/`schemas/**`，且 paper 不含 `m2-draft`、不写 `team*.yml`（2 个 it）。
- `scripts/desktop-plugin-delivery/logger-console-peer-singleton.spec.ts`：cosmokit/schemastery 出 deps 入 peer、`supports-color` 保留、版本 1.0.2（2 个 it）。
- `packages/workflow/worktree-registry/tests/peer-singleton.spec.ts`：dsh-brand/schemastery 出 deps 入 peer、zod 保留（2 个 it）。
- `apps/desktop-host/tests/devframe-deps.spec.ts`：desktop-host 含 §C 全部 19 行、不含 5 个禁用项、worktree-registry 恰好 1 行（3 个 it）。
- `apps/desktop-host/tests/peer-satisfaction.spec.ts`：满足/不满足/缺失/区间不符/非跟踪 peer 五种行为，含 fail-loud 文案片段断言（5 个 it）。

**亲自运行**（绕开 `pnpm exec`，直接 `node node_modules/vitest/vitest.mjs run` 指到这 6 个文件）：

```
Test Files  6 passed (6)
     Tests  34 passed (34)
  Duration  700ms
EXITCODE=0
```

与实现者自报“6 测试 34 用例绿”完全吻合（20+2+2+2+3+5=34）。

### 3. fail-loud 语义保持 —— 通过

- `apps/desktop-host/src/peer-satisfaction.ts`：`assertHostPeerSatisfaction` 在任一跟踪单例 peer 缺失或区间不满足时**立即 throw**（L131–132），无静默降级；错误文案 `renderPeerFailure` 与设计 §D.2 模板逐行对应（plugin/requires/host provides/action，含 `NOT INSTALLED`）。
- 接线位置：`index.ts` 于 `desktopComposition()` 内在 `assertHostPeerSatisfaction(...)`（L206），**早于** `boot()`（L349）与 `hostCtx.plugin(PluginPackages, ...)`（L352）——即在 cordis 实例化任何 bundle 之前的加载期校验，符合 §D.1。
- semver 手算复核：`^0.y.z` 钉死 minor（如 `^0.1.6` vs `0.1.7` 满足、vs `0.2.0` 拒绝）；`^1.x` 允许升 minor（`^1.2.3` vs `1.3.0` 满足、vs `2.0.0` 拒绝）；`~` 钉 minor 抬 patch；`>=` 单调非降。均与 semver 语义一致。`workspace:*` 区间短路放行（L62/L129），JSDoc 已说明依据：workspace 链接在仓内保证单实例，该短路只对发布产物的具体 semver 生效——合理设计决策。

### 4. 未越界 —— 通过

- **`apps/cli/package.json` 未被改**：本地副本与只读上游 `D:\dsh-upstream-latest\apps\cli\package.json` 逐字节一致（同为 0.1.6-alpha.1、无本任务 engines 字段、无 §C 追加行）；mtime 为 2026-09-16 22:43，早于本任务（9-19）。版本 0.1.6-alpha.1 系上游基线自带，非本任务所升。
- **`D:\dsh-upstream-latest` 未被改**：其 `apps/desktop-host/src/index.ts` mtime 仍为 2026-09-16；本次验收对其仅执行 Read。
- **无越界 package.json**：全仓 grep 新增 engines 串 `^22.19 || >=24` 恰好命中 20 个文件（18 experimental + worktree-registry + logger-console），无 experimental 目录外、vendor 其他包被波及。
- **无 npm publish 痕迹**：根 `package.json` 仅新增 `release:devframe:preflight`（L155），无 publish 脚本；`scripts/release/devframe-preflight.ts` 只跑 `pack --dry-run --json` 与本地断言，无 registry 调用。
- **无 git 操作痕迹**：本次验收未执行任何 git 命令；被改文件 mtime 均为今日且未提交，符合“只改不提交”的红线。

### 5. 存量 tsc 错误甄别 —— 通过（实现者说法属实）

- 工作副本 `packages/boot/app-boot/src/index.ts` 的再导出列表（L33–60）只含 `loadProfile`/`readProfileManifest`/`resolveBundleDir` 等，**确无** `loadProfileDirectory`、`PluginPackages` 导出。
- 但 `apps/desktop-host/src/index.ts` 对这两个符号的 import **在只读上游副本中逐字相同**（上游 L20、L22），且上游 `packages/boot/app-boot/src/` 有 3 个文件引用这两个符号——即上游 app-boot 是导出它们的。
- 结论：desktop-host 对这两个符号的引用是**上游既有**，本任务只新增了 `peer-satisfaction` 的 import 与一处 assert 调用；是未提交工作集里 app-boot 被重构删掉了这两个导出、而 desktop-host 未同步，造成的失配。**该 tsc 报错为存量，非本任务引入。**（注：我未跑全量 `tsc` 逐个数出“9”，但已独立定位根因并证实引用非本任务所加；“9 项”数量级与该失配一致。）

### 6. P0 实证（expert-pack-paper files）—— 通过

亲自对 `packages/experimental/expert-pack-paper` 跑 `npm pack --dry-run`（等价按 `files` 过滤）：

- tarball 共 27 个文件，含：`experts/` 9 个 `.md`、`schemas/` 6 个 `.schema.json`、`skills/` 4 个文件、`team.yml`。
- **不含** `team.m2-draft.yml`（该草稿文件经 `Test-Path` 确认**确实存在于磁盘**，故“缺席”是 files 排除生效，而非文件本就缺失）。
- 版本 0.1.6-alpha.1，退出码 0。

与设计 §A.17 / §B.1 断言 3 完全一致。

---

## 三、必须返工项

**无。**

---

## 四、遗留观察项（非阻断，不要求本次返工）

- **O1（设计已豁免）**：`devframe-profile/package.json` 的 `description` 仍写作 “Private profile bundle”。设计 §A.18 已明确删除 `private` 后该词仅为文案、不影响发布、不强制修改。无需处理。
- **O2（测试弱于设计字面，但已被其他层补强）**：`expert-pack-files.spec.ts` 断言的是 `package.json` 里**声明**的 files glob，而非设计 §E 字面所写的“pack --dry-run 实际 included files”。真实打包校验由 `scripts/release/devframe-preflight.ts` 的 `pack --dry-run --json` 负责，且我已亲自 `npm pack --dry-run` 实证。建议未来把该测试改成直接读 preflight 的实际文件列表，以闭合“声明 vs 产物”的差距。
- **O3（设计决策，记录在案）**：peer 校验对 `workspace:*` 区间 fail-open 放行。仓内开发/链接构建时这是对的（单实例由 workspace 链接保证），但意味着该守卫在“自包含 npm 包真正分发到空目录”的公网场景才完全生效——这正是 §B.2 空目录 install 验证要覆盖的闭环，而该步骤按红线本次未执行（需用户另行授权发布）。
