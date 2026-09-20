# 合并到单目录计划 v2

## 目标

让 `D:\dsh-devframe` 能直接启动客户端，不再依赖 `D:\dsh-upstream-latest`。

## 审核修正说明

根据子agent审核意见，v1 计划有以下问题：
1. **前提错误**：`D:\dsh-devframe` 里已经有 desktop 和 desktop-host 源码了，不需要复制
2. **真正的阻塞点**：`pnpm-workspace.yaml` 第 48 行有占位符，导致 `pnpm install` 报错
3. **electron 二进制没有安装**

## 执行步骤

### 第一步：修复 pnpm-workspace.yaml

**文件**：`D:\dsh-devframe\pnpm-workspace.yaml`

**改动**：
1. 把第 48 行的占位符 `electron-winstaller: set this to true or false` 改成 `electron-winstaller: false`
2. 补上 `msgpackr-extract: false`

### 第二步：安装依赖

运行 `pnpm install`，确保：
1. 所有依赖都安装成功
2. electron 二进制真正落地：`apps/desktop/node_modules/electron/dist/electron.exe` 存在

### 第三步：完善启动脚本

**文件**：`D:\dsh-devframe\.desktop-devframe-staging\dsh-client-launch.ps1`

**改动**：
- 确保有 `$env:DSH_HOME = 'C:\Users\25313\.dsh'` 这一行

### 第四步：测试启动

运行启动脚本，确认：
1. Electron 真正启动
2. 日志末尾有 "Quick Tunnel ready" 之类的成功标志
3. 客户端窗口正常打开

### 第五步：修改桌面快捷方式

测试通过后，把桌面 `DSH.lnk` 指向 `D:\dsh-devframe` 的启动脚本。

## 范围

**做**：
- 修复 `pnpm-workspace.yaml` 占位符
- 安装依赖
- 完善启动脚本
- 测试启动
- 修改桌面快捷方式

**不做**：
- 不复制 desktop 源码（已经有了）
- 不删旧目录 `D:\dsh-upstream-latest`
- 不做正式打包发布
- 不合并上游的其他包（browser-use、computer-use 等）

## 风险

1. **依赖版本冲突**：安装依赖时可能有版本冲突
2. **electron 下载失败**：可能需要手动下载 electron 二进制
3. **启动失败**：即使依赖装好了，也可能有其他配置问题

## 验收标准

1. 从 `D:\dsh-devframe` 启动客户端成功
2. 记忆库能正常打开和读取
3. 影子功能正常
4. 专家模式能正常打开
5. 桌面快捷方式指向 `D:\dsh-devframe`
