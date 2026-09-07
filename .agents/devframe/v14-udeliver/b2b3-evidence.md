# B2/B3 — Shadow/Memory 真实路径证据（b2b3-evidence）

基线：B1 已由总控定格 blocked/not_run（chain-evidence.md"chain5 收口"节=d6caf6f992；清单 765b20384d）；本文件只收 B2/B3。隔离面：DSH_HOME=`D:\dsh-udeliver-iso\home-b2b3`（settings+凭据引用），启动目录=`D:\dsh-udeliver-chain2`，overlay=`b2b3-overlay.yml`（shadow-router 补丁：authorizedRoots 双根+controllerProfile standard+shadowSessionId 声明式标记；project-memory 补丁：vaultRoot=`D:\dsh-udeliver-iso\vault-b2b3`+writeEnabled true；driver v2=d050a83b22，b2b3 模式零模型依赖）。代码树=修复版（bf198278cc 已并）。UI-adapter 边界=进程内 sessionController.create+真实 router/service/tool 面，非浏览器像素路径。

## Boot A（pwsh-215，后台启动立即返回）

| 步骤 | 命令/事件 | 结果（退出码/证据） |
| --- | --- | --- |
| boot 启动 | pwsh-215 后台 job | job 立即返回；node 进程 20s 内自行退出（driver appExit 生效）；port 3490 检查=非 LISTENING（进程已退，符合预期） |
| driver 挂载 | b2b3-driver.jsonl `driver-applied mode=b2b3` | ✅ |
| 影子会话创建 | `agent-created agentPreset=standard` session-7f0c9a52 | ✅ 声明式标记路径（shadowSessionId） |
| **B2 project_open** | `b2-open` | ✅ **真实成功**：workspaceId=bcd80c86-ed86-4788-8c5b-1148c3528b7e、controllerSessionId=shadow-fe079f37（路由预留）、bindingRevision=1、**state=ready**、canonicalPath=D:\dsh-udeliver-second |
| controller 收养+绑定 | `b2b3-error` | ❌ RemoteError：session "shadow-fe079f37" belongs to "D:\dsh-udeliver-second", not "D:\dsh-udeliver-chain2"（sessionController.create 的 cwd 归属校验；driver 传参缺陷，非产品缺陷）；appExit(1) 优雅退出验证生效（进程自净） |

**处置**：driver 修复（controller 收养改传 canonicalPath），同构零副本，重启 Boot A。失败步已按纪律记录为证据。
