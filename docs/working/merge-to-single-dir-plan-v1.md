# 合并到单目录计划 v1

## 目标

把 `D:\dsh-upstream-latest` 里有用的东西吸收到 `D:\dsh-devframe` 里，以后只用一个目录开发和启动客户端，不用再维护两个目录。

## 当前状态

- `D:\dsh-devframe`：主开发目录，有所有新包（project-memory、shadow-router 等）
- `D:\dsh-upstream-latest`：客户端启动目录，有 desktop 应用、desktop-host、node_modules 等

**问题**：两个目录并行维护，每次改代码都要同步，很容易出错。

## 方案

把 `D:\dsh-upstream-latest` 里有用的东西合并到 `D:\dsh-devframe`，以后直接从 `D:\dsh-devframe` 启动客户端。

## 具体步骤

### 第一步：复制 desktop 应用和 desktop-host

**复制内容**：
1. `apps/desktop/`（Electron 主进程）
2. `apps/desktop-host/`（host 后端服务）

**排除内容**：
- `node_modules/`（不复制，后面重新安装）
- `.desktop-build/`（不复制，这是构建缓存）

### 第二步：合并根目录配置

**需要检查并合并的文件**：
1. `package.json`（根目录的）
2. `pnpm-workspace.yaml`
3. `tsconfig*.json`
4. `tsdown.config.ts`
5. 其他根目录配置文件

**原则**：以 `D:\dsh-devframe` 为主，把 `D:\dsh-upstream-latest` 里新增的东西合并进来。

### 第三步：安装依赖

在 `D:\dsh-devframe` 里运行 `pnpm install`，安装所有依赖（包括 desktop 和 desktop-host 的）。

### 第四步：创建启动脚本

在 `D:\dsh-devframe` 下创建启动脚本：
- `.desktop-devframe-staging/dsh-client-launch.ps1`
- 指向 `D:\dsh-devframe\apps\desktop`

### 第五步：修改桌面快捷方式

把桌面快捷方式指向新的启动脚本。

### 第六步：测试启动

启动客户端，验证：
- 记忆库功能正常
- 影子功能正常
- 其他功能（专家模式等）正常

## 范围

**做**：
- 复制 desktop 和 desktop-host 源码
- 合并根目录配置
- 安装依赖
- 创建启动脚本
- 修改桌面快捷方式

**不做**：
- 不复制 node_modules
- 不复制 .desktop-build 缓存
- 不做正式打包发布
- 不清理旧目录 `D:\dsh-upstream-latest`（先保留，确认没问题再删）

## 风险

1. **依赖冲突**：合并后可能有依赖版本冲突，需要解决
2. **配置不兼容**：desktop 应用可能依赖某些特定的配置，需要调整
3. **构建问题**：新的目录结构可能导致构建失败

## 验收标准

1. 从 `D:\dsh-devframe` 启动客户端
2. 记忆库能正常打开和读取
3. 影子功能正常（打开新会话，历史加载正常）
4. 专家模式能正常打开
5. 其他原有功能正常
