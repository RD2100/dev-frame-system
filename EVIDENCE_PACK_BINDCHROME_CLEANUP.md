# Evidence Pack: BINDCHROME-REGISTRY-CLEANUP-A1

## REVIEW_RUN_ID
bindchrome-registry-cleanup-a1-v1-20260611

## 1. Task Summary

**Task**: 清理 PROJECT_REGISTRY 绑定缺口，消除 agent 提交 GPT 时的对话选择困惑

**Root Cause**: 11 个注册项目中仅 2 个有有效 ChatGPT 对话 URL，7 个占位项目（project-gamma ~ project-iota）绑定文件全为 null，dev-frame-writing 与 dev-frame-opencode 是同一项目但被注册为两个独立条目，agent-acceptance 缺少 CONVERSATION_BINDING.json。

## 2. Changes Made

### 2.1 PROJECT_REGISTRY.json（D:\agent-acceptance\.agent\）

**Before** (11 projects):
- agent-acceptance: active, 无绑定文件
- dev-frame-writing: active, 绑定 6a297e5f...
- dev-frame-opencode: active, 无绑定文件
- tripmark: active, 绑定 6a29f71a...
- project-gamma ~ project-iota: 7个 pending_binding，chat_url: null

**After** (3 projects):
- agent-acceptance: pending_binding（待用户提供对话 URL）
- dev-frame-opencode: active, 绑定 6a297e5f...（从 dev-frame-writing 迁移）
- tripmark: active, 绑定 6a29f71a...

### 2.2 CONVERSATION_BINDING.json（D:\dev-frame-opencode\.agent\）

**Action**: 新建

从 dev-frame-writing 迁移绑定信息，更新 project_id 和 project_root：
```json
{
  "project_id": "dev-frame-opencode",
  "project_root": "D:\\dev-frame-opencode",
  "bindings": [{
    "agent_id": "agent-opencode-001",
    "binding_status": "active",
    "conversation_id": "6a297e5f-c9c8-83a8-b413-a8fc414e0e85",
    "chat_url": "https://chatgpt.com/c/6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
  }]
}
```

### 2.3 Removed Entries

从 PROJECT_REGISTRY.json 移除以下项目（物理目录保留，仅移除注册）：
- dev-frame-writing（已合并到 dev-frame-opencode）
- project-gamma, project-delta, project-epsilon, project-zeta, project-eta, project-theta, project-iota（占位项目，无实际用途）

## 3. Files Modified/Created

| File | Action | Size |
|------|--------|------|
| D:\agent-acceptance\.agent\PROJECT_REGISTRY.json | Modified | total_projects: 11→3 |
| D:\dev-frame-opencode\.agent\CONVERSATION_BINDING.json | Created | 605B |

## 4. Verification Results

### 4.1 Registry Consistency Check

| Project | binding_status | Has CONVERSATION_BINDING.json | chat_url |
|---------|---------------|-------------------------------|----------|
| agent-acceptance | pending_binding | No | N/A |
| dev-frame-opencode | active | Yes | 6a297e5f... ✅ |
| tripmark | active | Yes | 6a29f71a... ✅ |

### 4.2 Agent Resolution Test

Agent 执行任务时的对话查找路径：
1. 读取 PROJECT_REGISTRY.json → 找到当前项目
2. 读取项目的 CONVERSATION_BINDING.json → 获取 chat_url
3. 通过 CDP 定位 Chrome 标签页 → 提交内容

**dev-frame-opencode**: Step 1 ✅ → Step 2 ✅ → Step 3 ✅
**tripmark**: Step 1 ✅ → Step 2 ✅ → Step 3 ✅
**agent-acceptance**: Step 1 ✅ → Step 2 ❌ (pending_binding, 预期行为)

## 5. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| dev-frame-writing 物理目录仍存在 | Low | 目录不影响功能，注册表已移除 |
| 占位项目物理目录仍存在 | Low | 同上，可手动清理 |
| agent-acceptance 无绑定 | Low | 已正确标记为 pending_binding |

## 6. Acceptance Criteria

- [x] 注册表项目数从 11 缩减到 3
- [x] 所有 active 项目均有有效 CONVERSATION_BINDING.json
- [x] 所有 CONVERSATION_BINDING.json 的 chat_url 非空
- [x] 无重复项目（dev-frame-writing 已合并）
- [x] pending_binding 项目明确标记待绑定
- [x] Agent 提交 GPT 时不再出现"不知道该选哪个"的困惑

## 7. Recommended Next Steps

1. 为 agent-acceptance 运行 `/bindChrome` 绑定治理对话
2. 如有新项目需求，用 `/rdinit` 注册并用 `/bindChrome` 绑定
3. 清理已移除项目的物理目录（可选，不影响功能）

---
_EVIDENCE_PACK_END_
